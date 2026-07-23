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

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusSlaveContext,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer

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


def build_context() -> ModbusServerContext:
    """
    Build the in-memory register tables. Sizes/addresses here mirror
    docs/hipot_register_map.md (using zero-based offsets, same convention
    as the register map's own sample code).

    Block sizes, with a little headroom over the documented address
    ranges so nothing overflows as fields get added later:
      co (coils)            -> 00001-00005  -> 5 used,  sized 10
      di (discrete inputs)  -> 10001-10007  -> 7 used,  sized 10
      ir (input registers)  -> 30001-30007  -> 7 used,  sized 10
      hr (holding registers)-> 40001-40015  -> 15 used, sized 20
    """

    coils = ModbusSequentialDataBlock(0, [0] * 10)
    discrete_inputs = ModbusSequentialDataBlock(0, [0] * 10)
    input_registers = ModbusSequentialDataBlock(0, [0] * 10)
    holding_registers = ModbusSequentialDataBlock(0, [0] * 20)

    # --- Dummy values, just to prove read plumbing works end to end ---

    # Discrete Inputs: pretend last test passed, device idle, interlock OK
    discrete_inputs.setValues(1, [1, 0, 0, 1, 0, 0, 1])  # addrs 10001-10007

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

def coil_watcher(coils: ModbusSequentialDataBlock):
    coils.setValues(1,1)
    while True:
        with lock: 
        ##Capture coil values with lock so threads do not touch data at same time        
            start_test = coils.getValues(1,1)[0]
            stop_test = coils.getValues(2,1)[0]
            reset_fault = coils.getValues(3,1)[0]
            remote_enable = coils.getValues(4,1)[0]
            offset_calibration = coils.getValues(5,1)[0]
            print(start_test)
        time.sleep(polling_period) ##200ms polling period
    
        


async def main():
    context, coils, discrete_inputs, input_registers, holding_registers  = build_context()
    print(f"Hi-pot Modbus TCP server starting on {HOST}:{PORT} (slave id {SLAVE_ID})")
    watcher_thread = threading.Thread(target=coil_watcher(coils), daemon=True)
    watcher_thread.start()  
    await StartAsyncTcpServer(context=context, address=(HOST, PORT))
    


if __name__ == "__main__":
    asyncio.run(main())