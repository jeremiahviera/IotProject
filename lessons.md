#Lessons learned

First I wrote the Hi pot tester simulator. I created a couple different classes to model a hipot tester in practice, so I can eventually connect it via modbus and create my IOT infra. One thing to point out is that the Tester sim was orignally designed for higher voltage equipment. 15kv default.On the next step when it was time to design the modbus register, i built it around a Chroma 19071/72/73 series tester. This testers values dont use 15kv as it is for much lower voltage UUTs. from this i decided to model the simulator around a much lower voltage UUT use case. 


Another issue I encountered is using the 16 bit register to store a flota. Voltage floats wont fit in a 16 bit register, I must combine 2 16 bit reg for a 32 bit float.
## concepts 
- Threading
Thread locking
async operation for server

-pymodbus
registers
reading/writing



# note dump
## hipot sim
hipot sim has 2 channels. one for reporting testing over modbus, and another to report machine health and state over other gateway
one state that will be reported on both will be the machine state, idle, running etc and faults. this must be exposed to modbus for machine functionality.

