"""
Quick smoke test for hipot_modbus_server.py -- run the server in one
terminal, this in another (or see the combined smoke test below).
"""
from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient("127.0.0.1", port=5020)
client.connect()

'''
di = client.read_discrete_inputs(address=0, count=7, slave=1)
print("Discrete Inputs (10001-10007):", di.bits[:7])

ir = client.read_input_registers(address=4, count=3, slave=1)
print("Input Registers (30005-30007):", ir.registers)

hr = client.read_holding_registers(address=0, count=15, slave=1)
print("Holding Registers (40001-40015):", hr.registers)
'''


# --- Test 1: Start Test while Remote Enable is still off ---
# Should print "Remote Control permission denied" on the server side,
# and NOT start a test.
print(">>> Writing Start Test with Remote Enable still OFF")
client.write_coil(address=0, value=True, slave=1)   # 00001 Start Test
time.sleep(0.5)  # give the watcher loop a chance to poll and react

co = client.read_coils(address=0, count=5, slave=1)
print("Coils after (should show Start Test self-cleared to False):", co.bits[:5])

# --- Test 2: Turn on Remote Enable, then Start Test for real ---
print("\n>>> Enabling Remote Enable")
client.write_coil(address=3, value=True, slave=1)   # 00004 Remote Enable
time.sleep(0.5)

print(">>> Writing Start Test with Remote Enable ON")
client.write_coil(address=0, value=True, slave=1)   # 00001 Start Test
time.sleep(0.5)

co = client.read_coils(address=0, count=5, slave=1)
print("Coils after (Start Test should be False, Remote Enable should stay True):", co.bits[:5])



client.close()