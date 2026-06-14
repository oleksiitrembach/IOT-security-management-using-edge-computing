"""Symulator urządzenia IoT. Publikuje telemetrię MQTT i zapisuje etykiety
odniesienia (ground truth). Każda replika kontenera = osobne urządzenie
(DEVICE_ID pobierany z nazwy hosta), więc `docker compose up --scale device=N`
tworzy N niezależnych urządzeń.
"""
import os, time, json, socket, csv, random
import paho.mqtt.client as mqtt

BROKER_HOST  = os.getenv("BROKER_HOST", "broker")
BROKER_PORT  = int(os.getenv("BROKER_PORT", "1883"))
DEVICE_ID    = os.getenv("DEVICE_ID") or socket.gethostname()
RATE         = float(os.getenv("RATE", "5"))          # komunikaty/s (norma)
DURATION     = float(os.getenv("DURATION", "120"))    # czas przebiegu [s]
SCENARIO     = os.getenv("SCENARIO", "mixed")         # normal|flood|payload|value|mixed
ANOMALY_RATE = float(os.getenv("ANOMALY_RATE", "0.05"))
DATA_DIR     = os.getenv("DATA_DIR", "/data")
MU           = float(os.getenv("MU", "25.0"))
SIGMA        = float(os.getenv("SIGMA", "1.5"))
FLOOD_BURST  = int(os.getenv("FLOOD_BURST", "40"))
PAYLOAD_BYTES= int(os.getenv("PAYLOAD_BYTES", "1024"))

os.makedirs(DATA_DIR, exist_ok=True)
gt = open(os.path.join(DATA_DIR, f"ground_truth_{DEVICE_ID}.csv"), "w", newline="")
gtw = csv.writer(gt)
gtw.writerow(["event_id", "device_id", "ts_pub", "is_anomaly", "anomaly_type"])

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id=f"sim-{DEVICE_ID}", protocol=mqtt.MQTTv5)
for _ in range(60):
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=30); break
    except Exception:
        time.sleep(1)
client.loop_start()

topic = f"iot/{DEVICE_ID}/telemetry"
counter = 0


def publish_event(value, is_anomaly, atype, pad=""):
    global counter
    counter += 1
    eid = f"{DEVICE_ID}-{counter}"
    ts = time.time()
    payload = {"event_id": eid, "device_id": DEVICE_ID, "ts_pub": ts,
               "value": value, "is_anomaly": is_anomaly, "anomaly_type": atype}
    if pad:
        payload["pad"] = pad
    client.publish(topic, json.dumps(payload), qos=0)
    gtw.writerow([eid, DEVICE_ID, f"{ts:.6f}", int(is_anomaly), atype])


start = time.time()
interval = 1.0 / RATE
while time.time() - start < DURATION:
    inject = (SCENARIO != "normal") and (random.random() < ANOMALY_RATE)
    if inject:
        kind = SCENARIO if SCENARIO in ("flood", "payload", "value") \
            else random.choice(["flood", "payload", "value"])
        if kind == "flood":
            for _ in range(FLOOD_BURST):
                publish_event(random.gauss(MU, SIGMA), True, "flood")
                time.sleep(0.005)
        elif kind == "payload":
            publish_event(random.gauss(MU, SIGMA), True, "payload", pad="X" * PAYLOAD_BYTES)
        else:  # skok wartości
            spike = MU + random.choice([-1, 1]) * (8 * SIGMA + random.random() * SIGMA)
            publish_event(spike, True, "value")
    else:
        publish_event(random.gauss(MU, SIGMA), False, "none")
    time.sleep(interval)

gt.flush(); gt.close()
client.loop_stop(); client.disconnect()
print(f"[sim {DEVICE_ID}] zakonczono, {counter} zdarzen")
