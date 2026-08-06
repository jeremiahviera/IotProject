# Edge Gateway — Modbus/HTTP → Sparkplug B (MQTT)

**Role in the stack (ISA-95 Level 2):** unifies two independent data sources on the field
device — live process values over Modbus TCP, and machine health / test traceability over a
separate HTTP interface (see `docs/hipot_register_map.md` for why those are split out of the
register map) — into a single coherent Sparkplug B payload, published to a cloud MQTT broker.
Nothing downstream (Level 3 ingestion, Level 4 dashboard) talks Modbus directly; this is the
only thing in the stack that does.

Source: `gateway/edge_gateway.py`

---

## Data sources polled each cycle (every `POLL_INTERVAL_S` = 2.0s)

| Source | Transport | Metrics | Why out-of-band (if applicable) |
|---|---|---|---|
| `hipot_modbus_server.py` | Modbus TCP, `127.0.0.1:5020` | `Test/MeasuredVoltage`, `Test/MeasuredCurrent`, `Test/ElapsedTimeS`, `Test/ResultCode`, `Test/UnderTest`, `Test/LastTestPass`, `Test/LastTestFail`, `Status/*` | — |
| `health_server.py` `/health` | HTTP, `127.0.0.1:5021` | `Health/*` (cycle count, uptime, internal temp, calibration state, fault code) | Real hi-pot testers don't expose service/diagnostic data over the same fieldbus as process control |
| `health_server.py` `/test_result` | HTTP, `127.0.0.1:5021` | `Test/TestId`, `Test/UnitSerial`, `Test/JobOrderId`, `Test/OperatorId`, `Test/FailReason` | Modbus has no native string type; these fields are inherently strings |

---

## Sparkplug B topic namespace

```
spBv1.0/SmartFactorySim/NBIRTH/EdgeNode1
spBv1.0/SmartFactorySim/DBIRTH/EdgeNode1/Device1
spBv1.0/SmartFactorySim/DDATA/EdgeNode1/Device1
spBv1.0/SmartFactorySim/NDEATH/EdgeNode1        (LWT, set on connect)
```

`GROUP_ID`, `EDGE_NODE_ID`, `DEVICE_ID` are set at the top of `edge_gateway.py`. One edge node,
one device today; a second rack tester would be a second `Device` registered on the same
`EdgeNode`, not a second gateway process.

---

## HiveMQ Cloud setup

The gateway connects to a hosted HiveMQ Cloud cluster over TLS rather than a local Mosquitto
broker — no broker to run or maintain locally, and it's reachable from anywhere for the
Level 3/4 work later.

1. **Create a cluster** at [HiveMQ Cloud](https://console.hivemq.cloud/) (free tier is enough
   for one gateway at a 2s poll interval — see limits below).
2. **Create credentials**: cluster → *Access Management* → add a username/password. The
   password is only shown once at creation time.
3. **Note the cluster URL** shown on the cluster's overview page
   (`xxxxxxxx.s1.eu.hivemq.cloud` or similar). Port is always **8883** (TLS) — HiveMQ Cloud
   does not offer a plaintext 1883 listener.
4. **Set credentials as environment variables**, not hardcoded — `edge_gateway.py` loads them
   via `python-dotenv`. Create a `.env` file in the project root (already covered by
   `.gitignore`):

   ```
   HIVEMQ_HOST=xxxxxxxx.s1.eu.hivemq.cloud
   HIVEMQ_USERNAME=edge-gateway
   HIVEMQ_PASSWORD=<the generated password>
   ```

5. **TLS**: the gateway uses `pysparkplug.TLSConfig()` with no arguments, which trusts the
   system's default CA store. That's sufficient because HiveMQ Cloud's certificate chains to a
   public CA — nothing to pin or supply manually.

**Free tier limits worth knowing:** 100 concurrent connections, ~10GB/month traffic. Comfortable
for one gateway; worth revisiting if this fans out to many rack testers on the same cluster.

---

## Failure handling

The gateway is meant to run unattended against field devices and a network link that isn't
always reliable, so each of its dependencies fails independently rather than taking the whole
process down with it.

| Scenario | Detection | Behavior |
|---|---|---|
| Modbus server not up yet when the gateway starts | `build_device()`'s initial connection attempt fails | Retries every `POLL_INTERVAL_S` until both Modbus and the health API are reachable, then births normally. Handles startup-ordering races (gateway started before its field device). |
| Modbus server stops cleanly (process exits, TCP FIN) | pymodbus's `recv()` sees an empty read and clears its own socket | Self-heals with no gateway-side code needed — the next poll's `execute()` sees a cleared socket and reconnects on its own. |
| Modbus connection drops **abruptly** (cable pull, crash, TCP RST) | `socket.send()` raises `OSError`/`BrokenPipeError`, which pymodbus does **not** catch or clear its socket for | Gateway catches `(ModbusException, OSError)` around `poll_modbus()` and explicitly calls `modbus_client.close()`, forcing a real reconnect attempt next cycle. Without this, pymodbus's sync client would keep "reconnecting" to a dead socket forever, since it only reconnects when its internal socket is `None`. |
| Modbus server killed while a read is in flight | pymodbus doesn't always raise here -- an incomplete/aborted exchange can come back as an `ExceptionResponse` (or other error PDU) with no `.registers`/`.bits`, which would otherwise raise an unhandled `AttributeError` deep inside `read_float()`, crashing the process. Confirmed by actually killing the Modbus server mid-run. | Every raw pymodbus call result is passed through a `_checked()` helper that calls `result.isError()` and raises `ModbusIOException` (a `ModbusException` subclass) before any `.registers`/`.bits` access. Falls into the same catch/reconnect path as the abrupt-drop case above. |
| Health/test-result HTTP API unreachable | `requests.exceptions.RequestException` (connection refused, timeout) | Caught independently of Modbus polling. Each `requests.get()` opens a fresh connection per call, so there's no persistent connection state to repair — it just succeeds again once the API is back. |
| One data source down, the other up | — | Modbus and HTTP polling are collected into `metrics` independently; a dead health API doesn't block live voltage/current from publishing, and vice versa. Only skips the publish entirely if **both** sources failed that cycle. |
| MQTT connection to HiveMQ Cloud drops | paho's own network loop (`loop_start()`, running in a background thread) | Reconnects automatically — `pysparkplug.Client` defaults to `reconnect_on_failure=True` with exponential backoff (1s–120s). No gateway code needed. |
| MQTT reconnects after a drop | `EdgeNode`'s internal `on_connect` callback (`pysparkplug` library code, not ours) | Re-publishes NBIRTH/DBIRTH and resets the Sparkplug sequence counter on **every** (re)connect — required by the Sparkplug B spec so downstream consumers know to discard stale state and re-sync. |
| Unexpected error (bug, malformed API response, schema change) | — | **Not caught.** Deliberately left to crash the process rather than looping silently forever. Only the specific, expected transient failure modes above are treated as "retry"; anything else is treated as "something is actually wrong" and fails loudly. |

---

## Known gaps / not handled

- **No store-and-forward buffering.** If HiveMQ Cloud is unreachable for an extended period,
  `paho`'s outgoing queue is unbounded by default (`ClientOptions.max_queued_messages = 0`
  means unlimited), so publishes queue up in memory rather than being dropped — but there's no
  persistent (on-disk) buffering. A long enough outage grows memory usage rather than losing
  data quietly; a genuinely long outage would still need attention.

---

## Quick start

```
# .env in project root (see HiveMQ Cloud setup above)
HIVEMQ_HOST=xxxxxxxx.s1.eu.hivemq.cloud
HIVEMQ_USERNAME=edge-gateway
HIVEMQ_PASSWORD=<password>

# terminal 1 — Modbus TCP server + health HTTP server (both started together)
python -m modbus_gateway.hipot_modbus_server

# terminal 2 — drive a test cycle so there's live data to see
python modbus_gateway/hipot_modbus_smoke.py

# terminal 3 — edge gateway
python -m gateway.edge_gateway
```

Verify in the HiveMQ Cloud console → *Web Client*, subscribed to `spBv1.0/SmartFactorySim/#`:
NBIRTH/DBIRTH on startup, then DDATA every ~2s with live voltage/current as a test runs.
