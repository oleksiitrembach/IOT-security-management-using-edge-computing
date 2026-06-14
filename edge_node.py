"""Węzeł brzegowy. W trybie DETECTION_LOCATION=edge wykonuje lokalną detekcję
i publikuje alerty (ze znacznikiem czasu wykrycia). W trybie central pozostaje
biernym elementem (detekcję wykonuje system centralny).
"""
import csv
import os
import time
import json
import threading

import psutil
import paho.mqtt.client as mqtt
from detector import Detector

BROKER_HOST = os.getenv("BROKER_HOST", "broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
MODE = os.getenv("DETECTION_LOCATION", "edge")
DATA_DIR = os.getenv("DATA_DIR", "/data")
STATS_INTERVAL = float(os.getenv("STATS_INTERVAL", "0.5"))

os.makedirs(DATA_DIR, exist_ok=True)
stats_path = os.path.join(DATA_DIR, "edge_stats.csv")
telemetry_path = os.path.join(DATA_DIR, "edge_telemetry.csv")

with open(telemetry_path, "w", newline="") as tf:
    writer = csv.writer(tf)
    writer.writerow(["event_id", "device_id", "ts_recv", "payload_len", "is_anomaly", "anomaly_type"])

with open(stats_path, "w", newline="") as sf:
    writer = csv.writer(sf)
    writer.writerow(["ts", "cpu_perc", "mem_mb"])

process = psutil.Process()

def _stats_worker():
    with open(stats_path, "a", newline="") as sf:
        writer = csv.writer(sf)
        process.cpu_percent(interval=None)
        while True:
            cpu = process.cpu_percent(interval=None)
            mem = process.memory_info().rss / 1024 / 1024
            writer.writerow([f"{time.time():.6f}", f"{cpu:.2f}", f"{mem:.2f}"])
            sf.flush()
            time.sleep(STATS_INTERVAL)


def _log_telemetry(data, payload_len):
    with open(telemetry_path, "a", newline="") as tf:
        writer = csv.writer(tf)
        writer.writerow([
            data.get("event_id"),
            data.get("device_id"),
            f"{time.time():.6f}",
            payload_len,
            int(data.get("is_anomaly", False)),
            data.get("anomaly_type", "none"),
        ])


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
    _log_telemetry(data, len(msg.payload))
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
threading.Thread(target=_stats_worker, daemon=True).start()
for _ in range(60):
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        break
    except Exception:
        time.sleep(1)
client.loop_forever()
