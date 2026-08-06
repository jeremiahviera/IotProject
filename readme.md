# Smart Factory Simulation Platform

A simulated industrial control stack modeled on the ISA-95 / Purdue Enterprise Reference
Architecture -- built to demonstrate real Modbus/MQTT/SQL/API patterns used in factory
automation, not a generic CRUD or IoT demo.

### Architecture

| Level | Layer | Status |
|---|---|---|
| 0/1 | Simulated machines (Python), each acting as a Modbus TCP field device | In progress -- hi-pot tester complete |
| 2 | Edge gateway: polls Modbus, translates to MQTT (Sparkplug B) | Complete -- publishes to HiveMQ Cloud |
| 3 | TimescaleDB ingestion + REST API (Node.js/Express) | Not started |
| 4 | React dashboard: OEE, alarms, predictive maintenance | Not started |

### Current status: Hi-Pot Tester (Phase 1)

A hi-pot (dielectric withstand) test station for a 480V low-voltage switchboard section,
grounded in UL 891 convention (test voltage = 2x rated AC voltage + 1000V) and modeled on
the Chroma 19071/19072/19073 instrument family, served over Modbus TCP.

- `simulators/base_machine.py` -- shared abstract `Machine` base class (state, calibration/
  wear tracking, health-sampling contract) for all future machine types.
- `simulators/hipot_tester.py` -- `HiPotTester(Machine)`: event-driven test cycle with
  graceful abort, time-driven health metrics.
- `modbus_gateway/hipot_modbus_server.py` -- pymodbus TCP server exposing the tester's
  command / status / measurement / setpoint registers.

Full register map, UUT rationale, and design notes: [`docs/hipot_register_map.md`](docs/hipot_register_map.md).
Coil command state machine: [`docs/hipot_coil_state_machine.png`](docs/hipot_coil_state_machine.png).

### Current status: Edge Gateway (Phase 2)

`gateway/edge_gateway.py` polls the hi-pot tester's Modbus registers and its out-of-band
health/test-result HTTP endpoints, unifies both into Sparkplug B, and publishes to a HiveMQ
Cloud broker over TLS. Built to keep running through the failures a field gateway actually
sees -- a Modbus server that isn't up yet, drops cleanly, or drops abruptly; a flaky health
API; an MQTT broker connection blip -- each handled independently rather than one failure
taking the whole gateway down.

Full HiveMQ Cloud setup, topic namespace, and the failure-handling table (what's detected, how,
and what happens): [`docs/edge_gateway.md`](docs/edge_gateway.md).

### UUT test parameters
| Parameter | New (480V switchboard section) | Why |
|---|---|---|
| `rated_test_voltage_v` | 2200.0 | 2×480+1000, DC hi-pot per UL/field convention |
| Test mode framing | DC | The formula and Chroma's DC range (50–6000V) both point to DC hi-pot for this class |
| `leakage_threshold_ma` | 2.0mA |2mA was chosen as a production-line pass/fail cutoff tight enough to catch a genuine insulation defect on a 480V-class switchboard while staying clear of the instrument's low-end noise floor (10µA)|
| `unit_serial` prefix| `SWB-2026-xxxx` (switchboard) | Matches the actual UUT type |
| `dwell_time_s` | 2.0 | Short for real HI POT factory context |
| `job_order_id` | keep pattern | Still fits — engineer-to-order jobs apply to switchboard builds too |



### Quick start

```
python3 -m venv myenv
source myenv/bin/activate        # myenv\Scripts\activate on Windows
pip install -r requirements.txt

# from the project root, in one terminal:
python -m modbus_gateway.hipot_modbus_server

# in a second terminal:
python modbus_gateway/hipot_modbus_smoke.py
```

To also run the edge gateway (publishes to HiveMQ Cloud -- see
[`docs/edge_gateway.md`](docs/edge_gateway.md) for cluster setup and `.env` values needed
first):

```
# in a third terminal:
python -m gateway.edge_gateway
```