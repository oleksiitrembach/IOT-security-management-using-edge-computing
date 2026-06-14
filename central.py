"""System centralny. Subskrybuje alerty (tryb edge) lub telemetrię (tryb
central, gdzie sam wykonuje detekcję). Utrwala wykrycia do data/detections.csv.
W wariancie centralnym kontener jest dodatkowo obciazany opoznieniem netem
(scripts/apply_netem.sh), co odwzorowuje droge do odleglej chmury.
"""
import os, time, json, csv, threading
import paho.mqtt.client as mqtt
from detector import Detector

BROKER_HOST = os.getenv("BROKER_HOST", "broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
MODE = os.getenv("DETECTION_LOCATION", "edge")
DATA_DIR = os.getenv("DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)

telemetry_path = os.path.join(DATA_DIR, "central_telemetry.csv")
telemetry_f = open(telemetry_path, "w", newline="")
telemetry_w = csv.writer(telemetry_f)
telemetry_w.writerow(["event_id", "device_id", "ts_recv", "payload_len", "is_anomaly", "anomaly_type"])
telemetry_f.flush()

det = Detector(
    freq_threshold=int(os.getenv("FREQ_THRESHOLD", "20")),
    max_payload=int(os.getenv("MAX_PAYLOAD", "512")),
    warmup=int(os.getenv("WARMUP", "30")),
    k_sigma=float(os.getenv("K_SIGMA", "4.0")),
)

lock = threading.Lock()
f = open(os.path.join(DATA_DIR, "detections.csv"), "w", newline="")
w = csv.writer(f); w.writerow(["event_id", "ts_alert", "reason", "source"]); f.flush()


def record(event_id, ts_alert, reason, source):
    with lock:
        w.writerow([event_id, f"{ts_alert:.6f}", reason, source]); f.flush()


def on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe("iot/+/telemetry", qos=0)
    client.subscribe("alerts", qos=0)
    print(f"[central] polaczono, tryb={MODE}")


def on_message(client, userdata, msg):
    if msg.topic == "alerts":
        if MODE == "edge":
            try:
                a = json.loads(msg.payload)
                record(a["event_id"], float(a["ts_alert"]), a.get("reason", "?"), "edge")
            except Exception:
                pass
        return
    try:
        data = json.loads(msg.payload)
    except Exception:
        return
    telemetry_w.writerow([
        data.get("event_id"),
        data.get("device_id"),
        f"{time.time():.6f}",
        len(msg.payload),
        int(data.get("is_anomaly", False)),
        data.get("anomaly_type", "none"),
    ])
    telemetry_f.flush()
    if MODE != "central":
        return
    flagged, reason = det.check(data["device_id"], float(data["value"]),
                                len(msg.payload), ts=time.time())
    if flagged:
        record(data["event_id"], time.time(), reason, "central")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id="central", protocol=mqtt.MQTTv5)
client.on_connect = on_connect
client.on_message = on_message
for _ in range(60):
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=30); break
    except Exception:
        time.sleep(1)
client.loop_forever()
