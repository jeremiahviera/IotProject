"""
hipot_modbus_smoke.py

Interactive smoke test for hipot_modbus_server.py -- run the server in one
terminal, this in another. Exercises the full wired-up path: writing a test
recipe into the setpoint holding registers, starting/aborting a test over
the command coils, and polling live voltage/current/elapsed-time input
registers plus the status discrete inputs while a test runs.
"""
from pymodbus.client import ModbusTcpClient
import time
import struct

client = ModbusTcpClient("127.0.0.1", port=5020)
client.connect()


def read_float(base_addr, slave=1):
    r = client.read_input_registers(address=base_addr, count=2, slave=slave)
    return struct.unpack('>f', struct.pack('>HH', r.registers[0], r.registers[1]))[0]


def read_live_voltage():
    return read_float(0)   # 30001-30002


def read_live_current():
    return read_float(2)   # 30003-30004


def read_elapsed_time():
    r = client.read_input_registers(address=4, count=1, slave=1)  # 30005
    return r.registers[0] / 10.0   # x0.1s scale, per the register map


def read_result_code():
    r = client.read_input_registers(address=6, count=1, slave=1)  # 30007
    return r.registers[0]


def read_status():
    co = client.read_coils(address=0, count=5, slave=1)
    di = client.read_discrete_inputs(address=0, count=8, slave=1)
    hr = client.read_holding_registers(address=0, count=15, slave=1)
    print("Coils             (00001-00005):", co.bits[:5])
    print("Discrete Inputs   (10001-10008):", di.bits[:8])
    print("Holding Registers (40001-40015):", hr.registers)


def enable_remote():
    print(">>> Enabling Remote Enable")
    client.write_coil(address=3, value=True, slave=1)   # 00004 Remote Enable


def write_setpoints(voltage_v, ramp_s, dwell_s, current_limit_ua):
    client.write_register(0, 1, slave=1)                  # 40001 Test Mode = DC
    client.write_register(1, int(voltage_v), slave=1)     # 40002 Voltage Setpoint
    client.write_register(2, int(ramp_s * 10), slave=1)   # 40003 Ramp Time
    client.write_register(3, int(dwell_s * 10), slave=1)  # 40004 Dwell Time
    client.write_register(4, int(dwell_s * 10), slave=1)  # 40005 Test Time
    hi = (int(current_limit_ua) >> 16) & 0xFFFF
    lo = int(current_limit_ua) & 0xFFFF
    client.write_registers(6, [hi, lo], slave=1)           # 40007-40008 Current High Limit
    print(f">>> Setpoints written: {voltage_v}V, {ramp_s}s ramp, "
          f"{dwell_s}s dwell, {current_limit_ua}uA high limit")


def poll_while_under_test():
    time.sleep(0.3)
    for _ in range(60):
        di = client.read_discrete_inputs(address=2, count=1, slave=1)  # 10003 Under Test
        if not di.bits[0]:
            break
        voltage = read_live_voltage()
        current = read_live_current()
        elapsed = read_elapsed_time()
        print(f"elapsed={elapsed:.1f}s  voltage={voltage:.1f}V  current={current:.1f}uA")
        time.sleep(0.5)
    print("Result code:", read_result_code(), "(1=PASS, 2=HIGH FAIL, 5=NO OUTPUT, 7=USER INTERRUPT)")
    read_status()


def trigger_test():
    print(">>> Starting a test")
    client.write_coil(address=0, value=True, slave=1)   # 00001 Start Test


def trigger_test_wpoll():
    print(">>> Starting a test, polling live values")
    trigger_test()
    poll_while_under_test()


def trigger_custom_test():
    write_setpoints(voltage_v=1000, ramp_s=2.0, dwell_s=1.0, current_limit_ua=5000)
    trigger_test_wpoll()


def trigger_test_abort():
    print(">>> Start test, then abort mid-ramp")
    trigger_test()
    time.sleep(1.5)
    client.write_coil(address=1, value=True, slave=1)   # 00002 Stop/Abort
    time.sleep(1.0)
    print("Result code (expect 7, USER INTERRUPT):", read_result_code())
    read_status()


def trigger_calibrate():
    print(">>> Running offset calibration")
    client.write_coil(address=4, value=True, slave=1)   # 00005 Run Offset Calibration
    time.sleep(2.5)
    read_status()


def print_menu():
    print("-----Modbus Server test-----")
    print("1. Start single test")
    print("2. Abort test (starts, waits 1.5s, then aborts)")
    print("3. Run offset calibration")
    print("4. Start test with live voltage/current/elapsed polling")
    print("5. Write custom setpoints (1000V/2.0s ramp/1.0s dwell/5000uA), then run + poll")
    print("6. Read full status snapshot")
    print("7. Enable Remote Enable")
    print("8. Display this menu")
    print("9. Exit")
    print("-----Please select an option-----")


print_menu()
running = True
while running:
    option_select = int(input())
    match option_select:
        case 1:
            trigger_test()
        case 2:
            trigger_test_abort()
        case 3:
            trigger_calibrate()
        case 4:
            trigger_test_wpoll()
        case 5:
            trigger_custom_test()
        case 6:
            read_status()
        case 7:
            enable_remote()
        case 8:
            print_menu()
        case 9:
            running = False
        case _:
            print("Unknown request. 8 for menu")

client.close()
