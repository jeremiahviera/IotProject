"""
hipot_modbus_server.py

This spins up a pymodbus server.
At this stage: register blocks are sized to match docs/hipot_register_map.md,
pre-loaded with dummy static values, and served over Modbus TCP. Nothing here
is connected to the actual HiPotTester simulator yet.

Run this file, then connect with any Modbus client (or our own test client)
pointed at 127.0.0.1:5020, slave id 1, and read the register blocks to
confirm the values below come back correctly.
"""

import asyncio
import threading
import time
import struct
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer
from modbus_gateway.health_server import create_health_app
from simulators.base_machine import MachineState
from simulators.hipot_tester import HiPotTester

# NOTE: pinned to pymodbus==3.7.4 (see requirements). pymodbus 3.14 rewrote
# the datastore internals (ModbusSlaveContext -> ModbusDeviceContext,
# setValues/getValues removed) in a way that's poorly documented as of this
# writing. 3.7.4 is the last release on the "classic" API that essentially
# all pymodbus tutorials/examples -- and the register map's own sample code
# -- assume.

HOST = "127.0.0.1"
PORT = 5020          # NOT 502 -- see earlier note on unprivileged ports
SLAVE_ID = 1
lock = threading.Lock() 
polling_period = 0.3 # time in ms | 0.2 would be 200ms
current_stop_event = None  # module-level, tracks the ACTIVE test's Event
latest_test_result_ref = {"value": None}  # shared with health_server's /test_result route



def build_context() -> ModbusServerContext:
    """
    Build the in-memory register tables. Sizes/addresses here mirror
    docs/hipot_register_map.md (using zero-based offsets, same convention
    as the register map's own sample code).

    Block sizes, with a little headroom over the documented address
    ranges so nothing overflows as fields get added later:
      co (coils)            -> 00001-00005  -> 5 used,  sized 10
      di (discrete inputs)  -> 10001-10008  -> 8 used,  sized 10
      ir (input registers)  -> 30001-30007  -> 7 used,  sized 10
      hr (holding registers)-> 40001-40015  -> 15 used, sized 20
    """

    coils = ModbusSequentialDataBlock(0, [0] * 10)
    discrete_inputs = ModbusSequentialDataBlock(0, [0] * 10)
    input_registers = ModbusSequentialDataBlock(0, [0] * 10)
    holding_registers = ModbusSequentialDataBlock(0, [0] * 20)

    # Enable remote
    coils.setValues(4,1)

    # Discrete Inputs: pretend last test passed, device idle, interlock OK,
    # no fault latched
    discrete_inputs.setValues(1, [1, 0, 0, 1, 0, 0, 1, 0])  # addrs 10001-10008

    # Input Registers: fake a plausible "last known" reading
    # 30005 Elapsed Time=0, 30006 Step=1, 30007 Result Code=1 (PASS)
    input_registers.setValues(5, [0, 1, 1])  # addrs 30005-30007

    # Holding Registers: pre-load with this UUT's real setpoints from the
    # register map (mode=DC, 2200V, 8.0s ramp, 2.0s dwell/test, 2000uA limit)
    holding_registers.setValues(1, [
        1,      # 40001 Test Mode = 1 (DC HiPot)
        2200,   # 40002 Voltage Setpoint (V)
        80,     # 40003 Ramp Time (x0.1s = 8.0s)
        20,     # 40004 Dwell Time (x0.1s = 2.0s)
        20,     # 40005 Test Time (x0.1s = 2.0s)
        0,      # 40006 Fall Time (not modeled -> 0)
        0, 2000,  # 40007-40008 Current High Limit (32-bit, = 2000uA)
        0, 0,     # 40009-40010 Current Low Limit (not modeled -> 0)
        0, 0,     # 40011-40012 Arc Current Limit (not modeled -> 0)
        0,      # 40013 AC Frequency (n/a, DC mode)
        0,      # 40014 GFI Enable (not modeled -> 0)
        0,      # 40015 Auto Range Enable (not modeled -> 0)
    ])

    slave_context = ModbusSlaveContext(
        di=discrete_inputs,
        co=coils,
        ir=input_registers,
        hr=holding_registers,
    )

    # single=False + explicit dict keyed by slave id -- matches
    # "Slave ID: 1" in the register map.
    server_context = ModbusServerContext(slaves={SLAVE_ID: slave_context}, single=False)
    return server_context, coils, discrete_inputs, input_registers, holding_registers

def health_sampler(tester, interval_s=5.0):
    while True:
        with lock:
            reading = tester.sample_health()
            metrics = reading.metrics
            if tester.state == MachineState.FAULT:
                 print("----WARNING: HIPOT SIM - FAULT DETECTED----")

            '''         
            print(f"[HEALTH] {tester.station_id}: "
                  f"state={tester.state.value} "
                  f"self_check={reading.self_check_status} "
                  f"metrics={reading.metrics}")
            '''
        time.sleep(interval_s)

def apply_setpoints(holding_registers, tester: HiPotTester):
    """Load whatever test recipe is currently sitting in the setpoint
    holding registers (40001-40015) into the tester -- mirrors a master
    writing config registers before writing the Start Test coil on a
    real hi-pot tester. Only the fields this simulator models are read;
    fall time / low limit / arc limit / GFI / auto-range stay
    documented-but-inert, per the register map."""
    voltage_setpoint_v = holding_registers.getValues(2, 1)[0]     # 40002
    ramp_time_x01s = holding_registers.getValues(3, 1)[0]         # 40003
    dwell_time_x01s = holding_registers.getValues(4, 1)[0]        # 40004
    hi, lo = holding_registers.getValues(7, 2)                    # 40007-40008
    current_high_limit_ua = (hi << 16) | lo

    tester.configure(
        test_voltage_v=voltage_setpoint_v,
        ramp_time_s=ramp_time_x01s / 10.0,
        dwell_time_s=dwell_time_x01s / 10.0,
        leakage_threshold_ma=current_high_limit_ua / 1000.0,
    )


def run_test(tester: HiPotTester, input_registers, discrete_inputs):
    global current_stop_event # Stop event to listen for test abortions
    stop_event = threading.Event()
    current_stop_event = stop_event
    with lock:
        discrete_inputs.setValues(3, [1])  # 10003 Under Test
        discrete_inputs.setValues(5, [1])  # 10005 HV Active

    def on_progress(elapsed_s: float, live_voltage: float, live_current_ma: float):
        ## Update live progress values
        with lock:
            ## Unpack voltage from float
            v_hi, v_lo = struct.unpack('>HH', struct.pack('>f', live_voltage))
            input_registers.setValues(1, [v_hi, v_lo])      # 30001-30002 Measured Voltage
            ## Measured Current is documented in uA -- tester reports mA
            c_hi, c_lo = struct.unpack('>HH', struct.pack('>f', live_current_ma * 1000.0))
            input_registers.setValues(3, [c_hi, c_lo])      # 30003-30004 Measured Current
            input_registers.setValues(5, [int(elapsed_s * 10)])  # 30005 Elapsed Time (x0.1s)
    print("")
    print("----INFO: HIPOT SIM - Test starting----")
    result = tester.run_test_cycle(
        unit_serial="SWB-2026-0001",   # placeholder for now
        job_order_id="JOB-4471",
        on_progress=on_progress,
        stop_event= stop_event
    )
    with lock:
        # write final result once the test completes -- codes match the
        # Result Codes table in the register map
        match result.result:
            case "PASS":
                print("INFO: HIPOT SIM - Test Passed")
                result_code = 1
            case "FAIL":
                if result.fail_reason == "LEAKAGE_EXCEEDED_THRESHOLD":
                    result_code = 2   # HIGH FAIL
                elif result.fail_reason == "VOLTAGE_RAMP_UNSTABLE":
                    result_code = 5   # NO OUTPUT
                else:
                    result_code = 2
                print("INFO: HIPOT SIM - Test Failed:", result.fail_reason)
            case "ABORTED":
                print("INFO: HIPOT SIM - Test Aborted")
                result_code = 7   # USER INTERRUPT
            case _:
                result_code = 0
        input_registers.setValues(7, [result_code])                 # 30007 Result Code
        discrete_inputs.setValues(3, [0])                            # 10003 Under Test = 0
        discrete_inputs.setValues(5, [0])                            # 10005 HV Active = 0
        discrete_inputs.setValues(1, [0, 0])                         # clear 10001/10002 before judging
        if result.result == "PASS":
            discrete_inputs.setValues(1, [1])
        elif result.result == "FAIL":
            discrete_inputs.setValues(2, [1])
        print("----INFO: HIPOT SIM - Test Finished----")
        print("")
    current_stop_event = None # Clear stop event


def abort_test(tester:HiPotTester, input_registers, discrete_inputs):
        print("INFO: HIPOT SIM - Aborting test")
        if current_stop_event:
            current_stop_event.set()   # Signal stop test
        
    
    
def run_calibrate(tester:HiPotTester):
    print("INFO: HIPOT SIM - Calibration starting")
    tester.calibrate()
    print("INFO: HIPOT SIM - Calibration finished")

def reset_fault(tester:HiPotTester):
    print("INFO: HIPOT SIM - Resetting Fault")
    tester.clear_fault()
    print("INFO: HIPOT SIM - State: ", tester.state)
    print("INFO: HIPOT SIM - Fault Reset")


def _store_test_result(result):
    """HiPotTester's on_test_result hook -- stashes the full TestResult
    (unit_serial, job_order_id, operator_id, fail_reason, etc.) so
    health_server's /test_result route can serve it out-of-band, the
    same way machine health is served out-of-band from Modbus."""
    with lock:
        latest_test_result_ref["value"] = result.to_dict()



def coil_watcher(coils: ModbusSequentialDataBlock, tester: HiPotTester, input_registers, discrete_inputs, holding_registers):
    while True:
        with lock:
            ## Capture coil values with lock so threads do not touch data at same time
            start_test = coils.getValues(1,1)[0]
            stop_test = coils.getValues(2,1)[0]
            reset_fault_cmd = coils.getValues(3,1)[0]
            remote_enable = coils.getValues(4,1)[0]
            offset_calibration = coils.getValues(5,1)[0]
            ## Capture testing state
            State = tester.state

            # Synced every poll regardless of which branch below runs --
            # a fault can be raised asynchronously by health_sampler, not
            # just from a coil write, and Remote Active should always
            # mirror the actual Remote Enable coil.
            discrete_inputs.setValues(7, [1 if remote_enable else 0])                  # 10007 Remote Active
            discrete_inputs.setValues(8, [1 if State == MachineState.FAULT else 0])    # 10008 Fault_latched

            if remote_enable: ## If remote modbus control is enabled. Should be, for sim purposes
                match State:
                    case MachineState.IDLE:
                        if start_test:
                            # Start test behavior
                            apply_setpoints(holding_registers, tester)
                            test_thread = threading.Thread(target= run_test, args= (tester, input_registers, discrete_inputs), daemon= True)
                            test_thread.start()
                            # Start test behavior
                        elif offset_calibration:
                            # Start calibration behavior
                            calibrate_thread = threading.Thread(target= run_calibrate, args=(tester,), daemon=True)
                            calibrate_thread.start()
                    case MachineState.RUNNING:
                        if stop_test:
                            abort_test(tester,input_registers, discrete_inputs)
                            # Stop test behavior
                    case MachineState.FAULT:
                        if reset_fault_cmd:
                            reset_fault(tester)
                        else:
                            print("ERROR: HIPOT SIM - Fault not clear, no action taken")
                    case MachineState.CALIBRATING:
                        print("INFO: HIPOT SIM - Calibrating")
                        ## When finished set back to idle
                    case MachineState.DOWN:
                        print("INFO: HIPOT SIM - System down")
                    case _:
                        print("ERROR: HIPOT SIM - System behavior unknown")

            else:
                print("WARNING: HIPOT SIM - Remote Control permission denied")

            #reset coil values
            coils.setValues(1, [0, 0, 0])   # clears 1-3: Start Test, Stop, Reset Fault
            coils.setValues(5, [0])
        time.sleep(polling_period) #the period the function polls
    
        


async def main():
    context, coils, discrete_inputs, input_registers, holding_registers  = build_context()
    tester = HiPotTester(station_id="HIPOT-01", on_test_result=_store_test_result)   # created ONCE, lives for the server's lifetime

    print(f"Hi-pot Modbus TCP server starting on {HOST}:{PORT} (slave id {SLAVE_ID})")
    # Create app instance for health band server
    app = create_health_app(tester, lock, latest_test_result_ref)
    # Start server procceses
    watcher_thread = threading.Thread(target=coil_watcher, args = (coils, tester, input_registers, discrete_inputs, holding_registers), daemon=True) # Watches for writes to registers
    watcher_thread.start()
    health_thread = threading.Thread(target=health_sampler, args=(tester,), daemon=True) # polls health data
    health_thread.start()
    server_thread = threading.Thread(
            target=app.run,
            kwargs={"port": 5021, "use_reloader": False},
            daemon=True,
        )
    server_thread.start()
    await StartAsyncTcpServer(context=context, address=(HOST, PORT))
    


if __name__ == "__main__":
    asyncio.run(main())