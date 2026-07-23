import struct

voltage = 2200.0
packed_bytes = struct.pack('>f', voltage)
print(packed_bytes)          # raw 4 bytes, e.g. b'\x45\x09\x00\x00'

hi, lo = struct.unpack('>HH', packed_bytes)
print(hi, lo)                 # 17673 0  <- these are what actually goes in registers 30001, 30002