# Hipot Simulator — Modbus Register Map

**Design basis:** Parameter ranges, test modes, and pass/fail behavior are grounded in the
Chroma 19071/19072/19073 Hipot Tester's real documented specifications (AC/DC/IR test modes,
voltage/current/time ranges, GFI, arc detection). The instrument itself uses a proprietary
serial protocol — this register map re-expresses those same real-world parameters as a
standard Modbus TCP/RTU interface, the way a protocol gateway would in an actual integration.

**Unit Under Test (UUT):** A low-voltage switchboard/MCC assembly section rated 480V,
tested per the standard field/industry DC hi-pot convention: **test voltage = 2 × rated AC
voltage + 1000V** (a 480V-rated assembly is treated as 600V-class, giving 2×480+1000 =
**2200V DC**). This is a routine production-line dielectric withstand test performed on
480V switchboards, MCCs, and panelboards before shipment — not a maintenance/field retest,
which is why dwell time here is short (seconds) rather than the multi-minute duration used
in field testing.

Slave ID: 1 (configurable) | Protocol: Modbus TCP (port 502) or RTU | Byte order: big-endian,
no word swap, for all 32-bit values

---

## Coils (Read/Write, 1-bit) — Commands

| Address | Name | Description |
|---|---|---|
| 00001 | Start Test | Write 1 to begin the active test step sequence |
| 00002 | Stop / Abort | Write 1 to immediately cut output and return to standby |
| 00003 | Reset Fault | Write 1 to clear a latched PASS/FAIL/fault state |
| 00004 | Remote Enable | 1 = accept Modbus control, 0 = front panel only |
| 00005 | Run Offset Calibration | Write 1 to trigger test-cable offset calibration (device performs a 5s measurement per Chroma's OFFSET routine) |

---

## Discrete Inputs (Read-only, 1-bit) — Status

| Address | Name | Description |
|---|---|---|
| 10001 | Test Pass | 1 = last completed test passed |
| 10002 | Test Fail | 1 = last completed test failed (any fail reason — see Result Code register for detail) |
| 10003 | Under Test | 1 = ramping, dwelling, or otherwise actively testing |
| 10004 | Safety Interlock OK | 0 = interlock open, HV output inhibited |
| 10005 | HV Active (Danger) | 1 = high voltage currently present at output terminal |
| 10006 | GFI Tripped | 1 = ground fault interrupt triggered (matches Chroma's GFI protection). **Not currently modeled by the simulator** — reserved for future use, always 0. |
| 10007 | Remote Active | 1 = device currently under remote (Modbus) control |

---

## Input Registers (Read-only, 16-bit) — Live Measurements

| Address | Name | Scale | Description |
|---|---|---|---|
| 30001–30002 | Measured Voltage | 32-bit float, V | Live output voltage, direct volts (no scaling) |
| 30003–30004 | Measured Current | 32-bit float, µA | Live leakage current in microamps |
| 30005 | Elapsed Time | x0.1s | Time since current step started |
| 30006 | Active Step Number | int | Which test step is currently running. Simulator currently runs a single-step DC withstand test (step = 1); multi-step sequences (e.g. hipot followed by IR) are a documented future extension. |
| 30007 | Test Result Code | enum | See **Result Codes** table below |

### Result Codes (register 30007)
Modeled on Chroma's documented fail categories. The simulator currently implements codes
0, 1, 2, and 5 (marked below); the rest are reserved for future extension (ARC FAIL, LOW
FAIL, GFI TRIPPED, and USER INTERRUPT are not yet modeled in `HiPotTester`).

| Code | Meaning | Implemented? |
|---|---|---|
| 0 | Standby / no result yet | Yes |
| 1 | PASS | Yes |
| 2 | HIGH FAIL — leakage current exceeded high limit (breakdown) | Yes (`LEAKAGE_EXCEEDED_THRESHOLD`) |
| 3 | LOW FAIL — leakage current below low limit (open circuit / bad contact) | Reserved |
| 4 | ARC FAIL — arc detected during test | Reserved |
| 5 | NO OUTPUT — voltage never reached target (bad connection) | Yes (`VOLTAGE_RAMP_UNSTABLE`) |
| 6 | GFI TRIPPED — ground fault interrupt | Reserved |
| 7 | USER INTERRUPT — test stopped manually | Reserved |

---

## Holding Registers (Read/Write, 16-bit) — Setpoints & Config

| Address | Name | Scale | Range | Description |
|---|---|---|---|---|
| 40001 | Test Mode | enum | 0–3 | 0=AC HiPot, 1=DC HiPot, 2=IR (Insulation Resistance), 3=GC (Ground Continuity). **This UUT uses mode 1 (DC HiPot).** |
| 40002 | Voltage Setpoint | x1 V | AC: 50–5000 / DC: 50–6000 / IR: 50–1000 | Target test voltage, direct volts. **This UUT: 2200V.** |
| 40003 | Ramp Time | x0.1 s | 0–9990 (0 = OFF) | Time to rise from 0 to setpoint. **This UUT: ~8.0s baseline (drifts upward with wear — see machine health notes).** |
| 40004 | Dwell Time | x0.1 s | 0–9990 (0 = OFF) | Hold time at setpoint before judging (DC/IR modes). **This UUT: 2.0s** (short production-line dwell, not a multi-minute field test). |
| 40005 | Test Time | x0.1 s | 0–9990 (0 = continuous) | Duration over which pass/fail is judged. Simulator treats this the same as Dwell Time for the DC withstand step. |
| 40006 | Fall Time | x0.1 s | 0–9990 (0 = OFF) | Time to fall from setpoint back to 0. **Not currently modeled by the simulator** — treat as 0 (OFF) until implemented. |
| 40007–40008 | Current High Limit | 32-bit int, x1 µA | AC: 100–20000 / DC: 10–5000 | Upper leakage threshold — breakdown trip. **This UUT: 2000µA (2.0mA)** — chosen to sit clear of the instrument's low-end noise floor while still catching a genuine insulation defect on 480V-class equipment, not simply centered in the instrument's measurable range. |
| 40009–40010 | Current Low Limit | 32-bit int, x1 µA | 0 (OFF) or above | Lower leakage threshold — open-circuit trip. **Not currently modeled by the simulator** — set to 0 (OFF). |
| 40011–40012 | Arc Current Limit | 32-bit int, x1 µA | 0 (OFF) or 1000–20000 | Arc detection threshold. **Not currently modeled** — set to 0 (OFF). |
| 40013 | AC Frequency | x1 Hz | 50 or 60 | Output frequency, AC mode only. Not applicable — this UUT runs DC mode. |
| 40014 | GFI Enable | bool | 0/1 | Ground fault interrupt on/off. **Not currently modeled** — set to 0. |
| 40015 | Auto Range Enable | bool | 0/1 | Auto current-range switching on/off. Not currently modeled — set to 0. |

---

## Machine Health / Diagnostic Data — Intentionally Out-of-Band

Asset-condition data (`ramp_time_actual_s` drift, `internal_temp_c`, `cycles_since_calibration`,
`last_calibration_date`, `self_check_status`, `fault_code`) is **not exposed through this Modbus
register map.**

Real hi-pot testers generally don't
expose internal diagnostic/service data over the same fieldbus interface used for process
values. That's commonly a separate maintenance/service interface, if it's exposed digitally
at all. Modeling it that way here keeps the Modbus surface lean (matching what a real
PLC/SCADA system would actually poll for process control) and gives the **edge gateway** a
genuine second job beyond simple protocol translation: it reads machine health directly from
the device object/service interface (out-of-band from Modbus) and unifies it with the
Modbus-sourced process data into a single coherent MQTT output.

---

## Example test sequence over the wire

1. Master writes `40001`–`40015` → configure Test Mode = 1 (DC), 2200V target, ~8.0s ramp,
   2.0s dwell/test time, fall time OFF, 2000µA (2.0mA) high limit, low/arc/GFI limits OFF
2. Master writes coil `00001` (Start Test) = 1
3. Device sets discrete input `10003` (Under Test) = 1, `10005` (HV Active) = 1
4. Master polls `30001`–`30007` every ~200ms during ramp/test to log live voltage/current
5. Test completes → `10003` = 0, `10001` or `10002` set, `30007` holds the result code
6. Master reads pass/fail and result code, logs it, writes coil `00003` (Reset Fault) if needed before the next DUT
7. Separately (out-of-band), the gateway reads machine health directly from the device and publishes it to MQTT on its own periodic cadence, independent of this test sequence

---

## Sample Python (pymodbus)

```python
from pymodbus.client import ModbusTcpClient
import struct

client = ModbusTcpClient('ip', port=502)
client.connect()

def write_float(client, base_addr, value, slave=1):
    packed = struct.pack('>f', value)
    hi, lo = struct.unpack('>HH', packed)
    client.write_registers(base_addr, [hi, lo], slave=slave)

def read_float(client, base_addr, slave=1):
    r = client.read_input_registers(base_addr, count=2, slave=slave)
    return struct.unpack('>f', struct.pack('>HH', r.registers[0], r.registers[1]))[0]

# Configure: 2200V DC, ~8.0s ramp, 2.0s dwell/test, high limit 2.0mA
client.write_register(40001 - 40001, 1, slave=1)             # DC HiPot mode
client.write_register(40002 - 40001, 2200, slave=1)          # 2200V
client.write_register(40003 - 40001, 80, slave=1)            # 8.0s ramp
client.write_register(40005 - 40001, 20, slave=1)            # 2.0s test/dwell
client.write_register(40006 - 40001, 0, slave=1)              # fall time OFF (not modeled)
client.write_registers(40007 - 40001, [0, 2000], slave=1)     # 2000uA (2.0mA) high limit
client.write_registers(40009 - 40001, [0, 0], slave=1)        # low limit OFF
client.write_register(40014 - 40001, 0, slave=1)               # GFI off (not modeled)

# Start test
client.write_coil(1 - 1, True, slave=1)

# Poll during test
voltage = read_float(client, 30001 - 30001)
current = read_float(client, 30003 - 30001)
print(f"Voltage: {voltage} V, Current: {current} uA")

# Check result
result = client.read_input_registers(30007 - 30001, count=1, slave=1)
print(f"Result code: {result.registers[0]}")
```

---

## Notes on design choices

- **UUT and test voltage are grounded in a real, sourced industry convention**, not an
  arbitrary value: 2200V DC comes from the standard field formula (2 × rated AC voltage +
  1000V) applied to a 480V-class low-voltage switchboard/MCC assembly, which is routinely
  hi-pot tested at the factory before shipment.
- **The 2.0mA leakage threshold was chosen to closely simulate a good cutoff for the UUT. It's tight enough to catch a genuine
  insulation defect on 480V-class equipment while staying clear of the instrument's low-end
  noise floor, and comfortably within the instrument's accurately-measurable DC current band. This number may be off to a real UUT.
- **Machine health/diagnostic data is intentionally out-of-band from this register map** —
  see the dedicated section above.
- **Several register groups (Fall Time, Current Low Limit, Arc Current Limit, GFI, multi-step
  sequencing) are defined in the map but not yet implemented in the simulator.** They're kept
  in the document because they're real, documented Chroma features and may be implemented as
  future extensions but each is out of scope for this project.
- **Direct-volt and direct-µA scaling** (no fractional multipliers) was chosen deliberately —
  it avoids the ambiguity of vendor-specific scale factors and keeps the map self-documenting,
  which matters if this is being reviewed by someone else on a team.
- **32-bit values pair two holding/input registers**, This detail causes bugs if left ambigous, documented here.
big-endian, no word swap
- **Zero-based addressing** is used in the code examples (subtracting the base address) since
  that's what actually goes out on the wire — the `4xxxx`/`3xxxx` prefixes are documentation
  convention only.