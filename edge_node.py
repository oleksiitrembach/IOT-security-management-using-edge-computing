"""Węzeł brzegowy. W trybie DETECTION_LOCATION=edge wykonuje lokalną detekcję
i publikuje alerty (ze znacznikiem czasu wykrycia). W trybie central pozostaje
biernym elementem (detekcję wykonuje system centralny).
"""
import os, time, json
import paho.mqtt.client as mqtt
from detector import Detector

BROKER_HOST = os.getenv("BROKER_HOST", "broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
MODE = os.getenv("DETECTION_LOCATION", "edge")

det = Detector(
    freq_threshold=int(os.getenv("FREQ_THRESHOLD", "20")),
    max_payload=int(os.getenv("MAX_PAYLOAD", "512")),
    warmup=int(os.getenv("WARMUP", "30")),
    k_sigma=float(os.getenv("K_SIGMA", "4.0")),
)


def on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe("iot/+/telemetry", qos=0)
    print(f"[edge] polaczono, tryb={MODE}")


def on_message(client, userdata, msg):
    if MODE != "edge":
        return
    try:
        data = json.loads(msg.payload)
    except Exception:
        return
    flagged, reason = det.check(data["device_id"], float(data["value"]),
                                len(msg.payload), ts=time.time())
    if flagged:
        alert = {"event_id": data["event_id"], "device_id": data["device_id"],
                 "ts_alert": time.time(), "reason": reason}
        client.publish("alerts", json.dumps(alert), qos=0)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id="edge-node", protocol=mqtt.MQTTv5)
client.on_connect = on_connect
client.on_message = on_message
for _ in range(60):
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=30); break
    except Exception:
        time.sleep(1)
client.loop_forever()
