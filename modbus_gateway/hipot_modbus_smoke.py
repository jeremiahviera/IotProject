"""
Quick smoke test for hipot_modbus_server.py -- run the server in one
terminal, this in another (or see the combined smoke test below).
"""
from pymodbus.client import ModbusTcpClient
import time
import struct

client = ModbusTcpClient("127.0.0.1", port=5020)
client.connect()
#client.write_coil(address=4, value=True, slave=1)   # Calibrate


def read_live_voltage(client):
    r = client.read_input_registers(address=0, count=2, slave=1)  # 30001-30002
    return struct.unpack('>f', struct.pack('>HH', r.registers[0], r.registers[1]))[0]

def read_elapsed_time(client):
    r = client.read_input_registers(address=4, count=1, slave=1)  # 30005
    return r.registers[0] / 10.0   # x0.1s scale, per the register map

def trigger_test(client):
    print(">>> Starting a test")
    client.write_coil(address=0, value=True, slave=1)   # 00001 Start Test

def trigger_test_wpoll(client):
    print(">>> Starting a test")
    client.write_coil(address=0, value=True, slave=1)   # 00001 Start Test
    time.sleep(0.5)

    # Poll every ~0.5s while the test is presumably running
    for _ in range(20):
        voltage = read_live_voltage(client)
        elapsed = read_elapsed_time(client)
        print(f"elapsed={elapsed:.1f}s  voltage={voltage:.1f}V")
        time.sleep(0.5)
    
def trigger_test_abort(client):
    print(">>> Start test with Aborting test")
    client.write_coil(address=0, value=True, slave=1)
    time.sleep(1.5)
    client.write_coil(address=1, value=True, slave=1)




print("-----Modbus Server test-----")
print("1. Start single test")
print("2. Abort test")
print("3. Calibrate")
print("4. Start test with auto log values")
print("5. display this menu")
print("6. exit")
print("-----Please select an option-----")
exit = False
while not exit:
    option_select = int(input())
    match option_select:
        case 1:
            trigger_test(client)
        case 2:
            trigger_test_abort(client)
        case 3:
            print("no def yet")
        case 4:
            trigger_test_wpoll(client)
        case 5:
            print("no def yet")
        case 6:
            print("no def yet")
        case _:
            print("Unknown request. 5 for menu")



client.close()