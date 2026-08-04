import struct
import time

import requests
from pymodbus.client import ModbusTcpClient
from pysparkplug import Metric, DataType, get_current_timestamp, Device, EdgeNode

MODBUS_SLAVE_ID = 1
HEALTH_URL = "http://127.0.0.1:5021/health"
TEST_RESULT_URL = "http://127.0.0.1:5021/test_result"
GROUP_ID = "SmartFactorySim"
EDGE_NODE_ID = "EdgeNode1"
DEVICE_ID = "Device1"
POLL_INTERVAL_S = 2.0  # seconds



def read_float(client, address, slave=MODBUS_SLAVE_ID):
    """Two consecutive input registers, big-endian -- reverses the
    struct.pack('>f', ...) your server does when writing them."""
    result = client.read_input_registers(address=address, count=2, slave=slave)
    return struct.unpack(">f", struct.pack(">HH", *result.registers))[0]

def poll_modbus(client) -> list[Metric]:
    ts = get_current_timestamp()
    
    voltage = read_float(client, address=0)
    current = read_float(client, address=2)
    elapsed_raw = client.read_input_registers(address=4, count=1, slave=MODBUS_SLAVE_ID).registers[0]  # 30005
    result_code = client.read_input_registers(address=6, count=1, slave=MODBUS_SLAVE_ID).registers[0]  # 30007

    discrete = client.read_discrete_inputs(address=0, count=8, slave=MODBUS_SLAVE_ID).bits
    last_test_pass = discrete[0] # 10001
    last_test_fail = discrete[1] # 10002
    under_test = discrete[2] # 10003
    safety_interlock = discrete[3] # 10004
    hv_active = discrete[4] # 10005
    gfi_tripped = discrete[5] # 10006
    remote_active = discrete[6] # 10007
    fault_latched = discrete[7] # 10008
    return [
        # Test/* -- product/quality data
        Metric(timestamp=ts, name="Test/MeasuredVoltage", datatype=DataType.FLOAT, value=voltage),
        Metric(timestamp=ts, name="Test/MeasuredCurrent", datatype=DataType.FLOAT, value=current),
        Metric(timestamp=ts, name="Test/ElapsedTimeS", datatype=DataType.FLOAT, value=elapsed_raw / 10.0),
        Metric(timestamp=ts, name="Test/ResultCode", datatype=DataType.INT32, value=result_code),
        Metric(timestamp=ts, name="Test/UnderTest", datatype=DataType.BOOLEAN, value=under_test),
        Metric(timestamp=ts, name="Test/LastTestPass", datatype=DataType.BOOLEAN, value=last_test_pass),
        Metric(timestamp=ts, name="Test/LastTestFail", datatype=DataType.BOOLEAN, value=last_test_fail),

        # Status/* -- instrument/asset condition
        Metric(timestamp=ts, name="Status/SafetyInterlock", datatype=DataType.BOOLEAN, value=safety_interlock),
        Metric(timestamp=ts, name="Status/HVActive", datatype=DataType.BOOLEAN, value=hv_active),
        Metric(timestamp=ts, name="Status/GFITripped", datatype=DataType.BOOLEAN, value=gfi_tripped),
        Metric(timestamp=ts, name="Status/RemoteActive", datatype=DataType.BOOLEAN, value=remote_active),
        Metric(timestamp=ts, name="Status/Fault", datatype=DataType.BOOLEAN, value=fault_latched),
    ]
    
def poll_health() -> list[Metric]:
    ts = get_current_timestamp()
    data = requests.get(HEALTH_URL, timeout=2.0).json()

    return [
        Metric(
            timestamp=ts,
            name="Health/CyclesSinceCalibration",
            datatype=DataType.INT32,
            value=data["cycles_since_calibration"],
        ),
        Metric(
            timestamp=ts,
            name="Health/DowntimeS",
            datatype=DataType.FLOAT,
            value=data["downtime_s"],
        ),
        Metric(
            timestamp=ts,
            name="Health/FaultCode",
            datatype=DataType.STRING,
            value=data["fault_code"],
        ),
        Metric(
            timestamp=ts,
            name="Health/LastCalibrationDate",
            datatype=DataType.STRING,
            value=data["last_calibration_date"],
        ),
        Metric(
            timestamp=ts,
            name="Health/InternalTemperatureC",
            datatype=DataType.FLOAT,
            value=data["metrics"]["internal_temp_c"],
        ),
        Metric(
            timestamp=ts,
            name="Health/RampTimeActualS",
            datatype=DataType.FLOAT,
            value=data["metrics"]["ramp_time_actual_s"],
        ),
        Metric(
            timestamp=ts,
            name="Health/ReadingId",
            datatype=DataType.STRING,
            value=data["reading_id"],
        ),
        Metric(
            timestamp=ts,
            name="Health/SelfCheckStatus",
            datatype=DataType.STRING,
            value=data["self_check_status"],
        ),
        Metric(
            timestamp=ts,
            name="Health/StationId",
            datatype=DataType.STRING,
            value=data["station_id"],
        ),
        Metric(
            timestamp=ts,
            name="Health/Timestamp",
            datatype=DataType.STRING,
            value=data["timestamp"],
        ),
        Metric(
            timestamp=ts,
            name="Health/TotalCycleCount",
            datatype=DataType.INT32,
            value=data["total_cycle_count"],
        ),
        Metric(
            timestamp=ts,
            name="Health/UptimeS",
            datatype=DataType.FLOAT,
            value=data["uptime_s"],
        ),
    ]
    

def poll_test_result() -> list[Metric]:
    """Traceability data for the last completed test -- same out-of-band
    HTTP channel as machine health, and for the same reason: Modbus has
    no native string type, so unit_serial/job_order_id/operator_id/
    fail_reason never went on the register map. Sourced from the last
    completed TestResult, not a live Modbus register."""
    ts = get_current_timestamp()
    response = requests.get(TEST_RESULT_URL, timeout=2.0)
    if response.status_code == 404:
        # No test has completed yet (e.g. right at startup) -- report
        # placeholders instead of failing the whole poll cycle.
        data = {
            "test_id": "",
            "unit_serial": "",
            "job_order_id": "",
            "operator_id": "",
            "fail_reason": None,
        }
    else:
        data = response.json()

    return [
        Metric(timestamp=ts, name="Test/TestId", datatype=DataType.STRING, value=data["test_id"]),
        Metric(timestamp=ts, name="Test/UnitSerial", datatype=DataType.STRING, value=data["unit_serial"]),
        Metric(timestamp=ts, name="Test/JobOrderId", datatype=DataType.STRING, value=data["job_order_id"]),
        Metric(timestamp=ts, name="Test/OperatorId", datatype=DataType.STRING, value=data["operator_id"]),
        Metric(timestamp=ts, name="Test/FailReason", datatype=DataType.STRING, value=data["fail_reason"]),
    ]

def build_device(client) -> Device:
    """Birth off a real sample. Retries until both the Modbus server and
    health server are reachable, so a startup-ordering race (gateway
    started before its field device / health server) doesn't crash the
    whole process."""
    while True:
        try:
            metrics = poll_modbus(client) + poll_health() + poll_test_result()
            return Device(device_id=DEVICE_ID, metrics=metrics)
        except Exception as e:
            print(f"WARNING: Waiting for Modbus/health server to become reachable: {e}")
            time.sleep(POLL_INTERVAL_S)

def main():
    modbus_client = ModbusTcpClient("127.0.0.1", port=5020)
    modbus_client.connect()

    device = build_device(modbus_client)

    edge_node = EdgeNode(group_id=GROUP_ID, edge_node_id=EDGE_NODE_ID, metrics=[])
    edge_node.register(device)
    edge_node.connect("127.0.0.1", port=1883, blocking=False)

    
    try:
        while True:
            try:
                metrics = poll_modbus(modbus_client) + poll_health() + poll_test_result()
                edge_node.update_device(DEVICE_ID, metrics=metrics)
            except Exception as e:
                print(f"WARNING: Error polling Modbus or Health: {e}")
            time.sleep(POLL_INTERVAL_S)
    except KeyboardInterrupt:
        print("Shutting down cleanly...")
    finally:
        edge_node.disconnect()
        modbus_client.close()
    
    
    
    
if __name__ == "__main__":
    main()