import time
from pysparkplug import Device, EdgeNode, Metric, DataType, get_current_timestamp

# Setup the MQTT broker connection parameters
BROKER_HOST = "localhost"
BROKER_PORT = 1883

GROUP_ID = "SmartFactorySim"
EDGE_NODE_ID = "EdgeNode1"
DEVICE_ID = "Device1"

# Declare birth schema
def build_device() -> Device:
    metrics = [
        Metric(timestamp = get_current_timestamp(),
               name = "Test/measuredVoltage",
               datatype = DataType.FLOAT,
               value = 230.0
                ),
        Metric(timestamp = get_current_timestamp(),
               name = "Status/Fault",
               datatype = DataType.BOOLEAN,
               value = False
                ),
    ]
    return Device(device_id = DEVICE_ID, metrics=metrics)

# Wire edge node
def main():
    device = build_device()
    edge_node = EdgeNode(group_id=GROUP_ID, edge_node_id=EDGE_NODE_ID, metrics=[])
    edge_node.connect(BROKER_HOST, port = BROKER_PORT, blocking= False)
    edge_node.register(device)
    
    # Connect to the MQTT broker and send the birth message
    print(f"Connecting to {BROKER_HOST}:{BROKER_PORT} ...")
    edge_node.connect(BROKER_HOST, port=BROKER_PORT, blocking=False)
    time.sleep(3.0)  # give the connect callback a moment to fire NBIRTH/DBIRTH

    try:
        voltage = 0.0
        while True:
            voltage += 100.0
            print(f"Publishing voltage: {voltage} ...")
            edge_node.update_device(
                DEVICE_ID,
                metrics=[
                    Metric(timestamp=get_current_timestamp(),
                           name="Test/measuredVoltage",
                           datatype=DataType.FLOAT,
                           value=voltage,
                    ),
                ],
            )
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("Disconnecting...")
    finally:
        edge_node.disconnect()
        print("Disconnected.")
        
if __name__ == "__main__":
    main()