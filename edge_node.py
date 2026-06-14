"""Węzeł brzegowy (edge node).

W trybie ``DETECTION_LOCATION=edge`` wykonuje lokalną detekcję anomalii
i publikuje alerty na temat ``alerts`` (ze znacznikiem czasu wykrycia).
W trybie ``central`` subskrybuje telemetrię, ale **nie** wykonuje detekcji
— logika jest przeniesiona do systemu centralnego.

Logowanie zasobów (CPU%, RAM) odbywa się wewnętrznie przez ``psutil``
z częstotliwością ``STATS_INTERVAL`` — daje to dokładniejszy pomiar procesu
niż ``docker stats`` z hosta. Dane trafiają do ``edge_stats.csv`` (PB3).

Graceful shutdown: sygnał SIGTERM powoduje flush wszystkich CSV i rozłączenie.
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
# Konfiguracja (zmienne środowiskowe)
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
stats_path = os.path.join(DATA_DIR, "edge_stats.csv")
telemetry_path = os.path.join(DATA_DIR, "edge_telemetry.csv")

stats_f = open(stats_path, "w", newline="")
stats_w = csv.writer(stats_f)
stats_w.writerow(["ts", "cpu_perc", "mem_mb"])
stats_f.flush()

telemetry_f = open(telemetry_path, "w", newline="")
telemetry_w = csv.writer(telemetry_f)
telemetry_w.writerow(["event_id", "device_id", "ts_recv", "payload_len",
                       "is_anomaly", "anomaly_type"])
telemetry_f.flush()

# ---------------------------------------------------------------------------
# Wątek zbierający statystyki zasobów (psutil)
# ---------------------------------------------------------------------------
process = psutil.Process()
_shutdown = threading.Event()


def _stats_worker():
    """Zbiera CPU% i RAM procesu edge co STATS_INTERVAL sekund.

    Używamy ``psutil.Process`` zamiast ``docker stats``, bo:
    - mierzymy *proces*, nie cały kontener (precyzyjniejsze),
    - nie zależy od hosta (działa w CI/Codespaces),
    - eliminuje podwójne nadpisywanie pliku stats.
    """
    process.cpu_percent(interval=None)  # pierwsza próbka (inicjalizacja)
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
# Detektor
# ---------------------------------------------------------------------------
det = Detector(
    freq_threshold=int(os.getenv("FREQ_THRESHOLD", "20")),
    max_payload=int(os.getenv("MAX_PAYLOAD", "512")),
    warmup=int(os.getenv("WARMUP", "30")),
    k_sigma=float(os.getenv("K_SIGMA", "4.0")),
)

# ---------------------------------------------------------------------------
# Liczniki (do podsumowania)
# ---------------------------------------------------------------------------
_msg_count = 0
_alert_count = 0
_msg_lock = threading.Lock()


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------
def on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe("iot/+/telemetry", qos=0)
    print(f"[edge] polaczono, tryb={MODE}, detektor={det}")


def on_message(client, userdata, msg):
    global _msg_count, _alert_count

    try:
        data = json.loads(msg.payload)
    except Exception:
        return

    with _msg_lock:
        _msg_count += 1

    # Logowanie telemetrii (zawsze — potrzebne do Tabeli 7: straty pakietów)
    telemetry_w.writerow([
        data.get("event_id"),
        data.get("device_id"),
        f"{time.time():.6f}",
        len(msg.payload),
        int(data.get("is_anomaly", False)),
        data.get("anomaly_type", "none"),
    ])
    telemetry_f.flush()

    # Detekcja tylko w trybie edge
    if MODE != "edge":
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
        alert = {
            "event_id": data["event_id"],
            "device_id": data["device_id"],
            "ts_alert": time.time(),
            "reason": reason,
        }
        client.publish("alerts", json.dumps(alert), qos=0)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
def _shutdown_handler(signum, frame):
    print(f"[edge] shutdown (signal={signum}), msgs={_msg_count}, "
          f"alerts={_alert_count}")
    _shutdown.set()
    stats_f.flush()
    stats_f.close()
    telemetry_f.flush()
    telemetry_f.close()
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
