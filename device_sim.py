"""Symulator urządzenia IoT.

Publikuje telemetrię MQTT i zapisuje etykiety odniesienia (ground truth).
Każda replika kontenera = osobne urządzenie (``DEVICE_ID`` pobierany
z nazwy hosta), więc ``docker compose up --scale device=N`` tworzy
N niezależnych urządzeń (PB5 — skalowalność).

Scenariusze anomalii (mapowanie na Tabelę 3 pracy):
- ``normal``  — wyłącznie ruch normalny (S1: FPR, zasoby)
- ``mixed``   — mix anomalii 5% (S2: skalowalność)
- ``flood``   — zalewanie komunikatami (S3: czas detekcji, czułość)
- ``payload`` — anomalia rozmiaru ładunku (S4: czas detekcji, precyzja)
- ``value``   — skok wartości statystycznej (anomalia k-sigma)
"""

import os
import sys
import signal
import time
import json
import socket
import csv
import random

import paho.mqtt.client as mqtt

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
BROKER_HOST = os.getenv("BROKER_HOST", "broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID") or socket.gethostname()
RATE = float(os.getenv("RATE", "5"))              # komunikaty/s (norma)
DURATION = float(os.getenv("DURATION", "120"))     # czas przebiegu [s]
SCENARIO = os.getenv("SCENARIO", "mixed")
ANOMALY_RATE = float(os.getenv("ANOMALY_RATE", "0.05"))
DATA_DIR = os.getenv("DATA_DIR", "/data")
MU = float(os.getenv("MU", "25.0"))
SIGMA = float(os.getenv("SIGMA", "1.5"))
FLOOD_BURST = int(os.getenv("FLOOD_BURST", "40"))
PAYLOAD_BYTES = int(os.getenv("PAYLOAD_BYTES", "1024"))
FLUSH_EVERY = int(os.getenv("FLUSH_EVERY", "50"))  # flush GT co N zdarzeń

os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Ground truth (etykiety odniesienia do Tabeli 5)
# ---------------------------------------------------------------------------
gt_path = os.path.join(DATA_DIR, f"ground_truth_{DEVICE_ID}.csv")
gt = open(gt_path, "w", newline="")
gtw = csv.writer(gt)
gtw.writerow(["event_id", "device_id", "ts_pub", "is_anomaly", "anomaly_type"])
gt.flush()

# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id=f"sim-{DEVICE_ID}", protocol=mqtt.MQTTv5)
if os.getenv("MQTT_TLS"):
    client.tls_set(ca_certs=os.getenv("MQTT_CA"))
    if os.getenv("MQTT_USER") and os.getenv("MQTT_PASS"):
        client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS"))

for attempt in range(60):
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        break
    except Exception:
        time.sleep(1)
else:
    print(f"[sim {DEVICE_ID}] nie mozna polaczyc z brokerem", file=sys.stderr)
    sys.exit(1)
client.loop_start()

topic = f"iot/{DEVICE_ID}/telemetry"
counter = 0


# ---------------------------------------------------------------------------
# Publikowanie
# ---------------------------------------------------------------------------
def publish_event(value, is_anomaly, atype, pad=""):
    """Publikuje jedno zdarzenie telemetryczne i rejestruje w ground truth."""
    global counter
    counter += 1
    eid = f"{DEVICE_ID}-{counter}"
    ts = time.time()
    payload = {
        "event_id": eid,
        "device_id": DEVICE_ID,
        "ts_pub": ts,
        "value": value,
        "is_anomaly": is_anomaly,
        "anomaly_type": atype,
    }
    if pad:
        payload["pad"] = pad
    client.publish(topic, json.dumps(payload), qos=0)
    gtw.writerow([eid, DEVICE_ID, f"{ts:.6f}", int(is_anomaly), atype])
    # Flush co FLUSH_EVERY zdarzeń — kompromis wydajność vs bezpieczeństwo
    if counter % FLUSH_EVERY == 0:
        gt.flush()


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
def _shutdown(signum, frame):
    gt.flush()
    gt.close()
    client.loop_stop()
    client.disconnect()
    print(f"[sim {DEVICE_ID}] shutdown (signal={signum}), {counter} zdarzen")
    sys.exit(0)


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT, _shutdown)

# ---------------------------------------------------------------------------
# Główna pętla
# ---------------------------------------------------------------------------
print(f"[sim {DEVICE_ID}] start: scenario={SCENARIO}, rate={RATE}/s, "
      f"duration={DURATION}s, anomaly_rate={ANOMALY_RATE}")

start = time.time()
interval = 1.0 / RATE

while time.time() - start < DURATION:
    inject = (SCENARIO != "normal") and (random.random() < ANOMALY_RATE)

    if inject:
        kind = (SCENARIO if SCENARIO in ("flood", "payload", "value")
                else random.choice(["flood", "payload", "value"]))

        if kind == "flood":
            for _ in range(FLOOD_BURST):
                publish_event(random.gauss(MU, SIGMA), True, "flood")
                time.sleep(0.005)
        elif kind == "payload":
            publish_event(random.gauss(MU, SIGMA), True, "payload",
                          pad="X" * PAYLOAD_BYTES)
        else:  # skok wartości (k-sigma)
            spike = MU + random.choice([-1, 1]) * (8 * SIGMA + random.random() * SIGMA)
            publish_event(spike, True, "value")
    else:
        publish_event(random.gauss(MU, SIGMA), False, "none")

    time.sleep(interval)

# Flush końcowy
gt.flush()
gt.close()
client.loop_stop()
client.disconnect()
print(f"[sim {DEVICE_ID}] zakonczono, {counter} zdarzen")
