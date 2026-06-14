"""System centralny (central system).

W trybie ``DETECTION_LOCATION=edge`` subskrybuje temat ``alerts`` i loguje
wykrycia dokonane przez węzeł brzegowy. W trybie ``central`` sam wykonuje
detekcję na danych telemetrycznych — identyczna logika jak na edge, ale
w kontenerze obciążonym opóźnieniem sieciowym ``tc netem``
(patrz ``scripts/apply_netem.sh``).

Loguje:
- ``detections.csv`` — wykrycia (event_id, ts_alert, reason, source)
- ``central_telemetry.csv`` — odebrana telemetria (do obliczania strat pakietów)
- ``central_stats.csv`` — CPU/RAM procesu centralnego (do porównania z edge, PB3)

Graceful shutdown: SIGTERM → flush CSV, rozłączenie.
"""

import csv
import os
import signal
import sys
import time
import json
import threading

import psutil
import paho.mqtt.client as mqtt
from detector import Detector

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------
BROKER_HOST = os.getenv("BROKER_HOST", "broker")
BROKER_PORT = int(os.getenv("BROKER_PORT", "1883"))
MODE = os.getenv("DETECTION_LOCATION", "edge")
DATA_DIR = os.getenv("DATA_DIR", "/data")
STATS_INTERVAL = float(os.getenv("STATS_INTERVAL", "0.5"))

os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Pliki wyjściowe
# ---------------------------------------------------------------------------
telemetry_path = os.path.join(DATA_DIR, "central_telemetry.csv")
telemetry_f = open(telemetry_path, "w", newline="")
telemetry_w = csv.writer(telemetry_f)
telemetry_w.writerow(["event_id", "device_id", "ts_recv", "payload_len",
                       "is_anomaly", "anomaly_type"])
telemetry_f.flush()

detections_path = os.path.join(DATA_DIR, "detections.csv")
det_f = open(detections_path, "w", newline="")
det_w = csv.writer(det_f)
det_w.writerow(["event_id", "ts_alert", "reason", "source"])
det_f.flush()

stats_path = os.path.join(DATA_DIR, "central_stats.csv")
stats_f = open(stats_path, "w", newline="")
stats_w = csv.writer(stats_f)
stats_w.writerow(["ts", "cpu_perc", "mem_mb"])
stats_f.flush()

det_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Wątek zbierający statystyki zasobów centralnego (psutil)
# ---------------------------------------------------------------------------
process = psutil.Process()
_shutdown = threading.Event()


def _stats_worker():
    """Zbiera CPU% i RAM procesu centralnego co STATS_INTERVAL sekund."""
    process.cpu_percent(interval=None)
    while not _shutdown.is_set():
        try:
            cpu = process.cpu_percent(interval=None)
            mem = process.memory_info().rss / 1024 / 1024
            stats_w.writerow([f"{time.time():.6f}", f"{cpu:.2f}", f"{mem:.2f}"])
            stats_f.flush()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
        _shutdown.wait(STATS_INTERVAL)


# ---------------------------------------------------------------------------
# Detektor (identyczna konfiguracja jak na edge — izolujemy lokalizację)
# ---------------------------------------------------------------------------
det = Detector(
    freq_threshold=int(os.getenv("FREQ_THRESHOLD", "20")),
    max_payload=int(os.getenv("MAX_PAYLOAD", "512")),
    warmup=int(os.getenv("WARMUP", "30")),
    k_sigma=float(os.getenv("K_SIGMA", "4.0")),
)

# ---------------------------------------------------------------------------
# Liczniki
# ---------------------------------------------------------------------------
_msg_count = 0
_alert_count = 0
_msg_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def record(event_id, ts_alert, reason, source):
    """Zapisuje wykrycie do detections.csv (thread-safe)."""
    with det_lock:
        det_w.writerow([event_id, f"{ts_alert:.6f}", reason, source])
        det_f.flush()


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------
def on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe("iot/+/telemetry", qos=0)
    client.subscribe("alerts", qos=0)
    print(f"[central] polaczono, tryb={MODE}")


def on_message(client, userdata, msg):
    global _msg_count, _alert_count

    # Alerty z edge (tryb brzegowy)
    if msg.topic == "alerts":
        if MODE == "edge":
            try:
                a = json.loads(msg.payload)
                record(a["event_id"], float(a["ts_alert"]),
                       a.get("reason", "?"), "edge")
                with _msg_lock:
                    _alert_count += 1
            except Exception:
                pass
        return

    # Telemetria z urządzeń
    try:
        data = json.loads(msg.payload)
    except Exception:
        return

    with _msg_lock:
        _msg_count += 1

    # Logowanie telemetrii (zawsze — potrzebne do Tabeli 7)
    telemetry_w.writerow([
        data.get("event_id"),
        data.get("device_id"),
        f"{time.time():.6f}",
        len(msg.payload),
        int(data.get("is_anomaly", False)),
        data.get("anomaly_type", "none"),
    ])
    telemetry_f.flush()

    # Detekcja tylko w trybie central
    if MODE != "central":
        return

    flagged, reason = det.check(
        data["device_id"],
        float(data["value"]),
        len(msg.payload),
        ts=time.time(),
    )
    if flagged:
        with _msg_lock:
            _alert_count += 1
        record(data["event_id"], time.time(), reason, "central")


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
def _shutdown_handler(signum, frame):
    print(f"[central] shutdown (signal={signum}), msgs={_msg_count}, "
          f"alerts={_alert_count}")
    _shutdown.set()
    for fh in (telemetry_f, det_f, stats_f):
        try:
            fh.flush()
            fh.close()
        except Exception:
            pass
    try:
        client.disconnect()
    except Exception:
        pass
    sys.exit(0)


signal.signal(signal.SIGTERM, _shutdown_handler)
signal.signal(signal.SIGINT, _shutdown_handler)

# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                     client_id="central", protocol=mqtt.MQTTv5)
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
