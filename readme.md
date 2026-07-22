### unit under test for hipot sim
480v UL 891

### test parameters for hipot simulation
| Parameter | New (480V switchboard section) | Why |
|---|---|---|
| `rated_test_voltage_v` | 2200.0 | 2×480+1000, DC hi-pot per UL/field convention |
| Test mode framing | DC | The formula and Chroma's DC range (50–6000V) both point to DC hi-pot for this class |
| `leakage_threshold_ma` | 2.0mA |2mA was chosen as a production-line pass/fail cutoff tight enough to catch a genuine insulation defect on a 480V-class switchboard while staying clear of the instrument's low-end noise floor (10µA)|
| `unit_serial` prefix| `SWB-2026-xxxx` (switchboard) | Matches the actual UUT type |
| `dwell_time_s` | 2.0 | Short for real HI POT factory context |
| `job_order_id` | keep pattern | Still fits — engineer-to-order jobs apply to switchboard builds too |