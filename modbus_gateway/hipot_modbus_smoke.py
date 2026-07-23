"""
Quick smoke test for hipot_modbus_server.py -- run the server in one
terminal, this in another (or see the combined smoke test below).
"""
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=5020)
client.connect()

di = client.read_discrete_inputs(address=0, count=7, slave=1)
print("Discrete Inputs (10001-10007):", di.bits[:7])

ir = client.read_input_registers(address=4, count=3, slave=1)
print("Input Registers (30005-30007):", ir.registers)

hr = client.read_holding_registers(address=0, count=15, slave=1)
print("Holding Registers (40001-40015):", hr.registers)

client.close()