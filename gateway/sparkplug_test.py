import time
import os
from pysparkplug import Device, EdgeNode, Metric, DataType, get_current_timestamp, Client, TLSConfig
from dotenv import load_dotenv

load_dotenv()
'''
# local mqtt host params
BROKER_HOST = "localhost"
BROKER_PORT = 1883
'''
MQTT_HOST = os.environ["HIVEMQ_HOST"]
MQTT_PORT = 8883
MQTT_USERNAME = os.environ["HIVEMQ_USERNAME"]
MQTT_PASSWORD = os.environ["HIVEMQ_PASSWORD"]
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
    
    mqtt_client = Client(
        client_id=EDGE_NODE_ID,
        username=MQTT_USERNAME,
        password=MQTT_PASSWORD,
        transport_config=TLSConfig(),  # defaults trust the system CA store,
    )                                  # which is enough for HiveMQ Cloud's public-CA certificate
                          
    device = build_device()
    edge_node = EdgeNode(group_id=GROUP_ID, edge_node_id=EDGE_NODE_ID, metrics=[], client=mqtt_client)
    edge_node.register(device)
    edge_node.connect(MQTT_HOST, port = MQTT_PORT, blocking= False)

    # Connect to the MQTT broker and send the birth message
    print(f"Connecting to {MQTT_HOST}:{MQTT_PORT} ...")
    edge_node.connect(MQTT_HOST, port=MQTT_PORT, blocking=False)
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