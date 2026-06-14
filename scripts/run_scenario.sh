#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_scenario.sh — jeden przebieg jednego scenariusza
# ---------------------------------------------------------------------------
# Przykłady:
#   DETECTION_LOCATION=edge SCENARIO=flood DURATION=120 ./scripts/run_scenario.sh
#   DETECTION_LOCATION=central SCENARIO=mixed DURATION=120 LATENCY=60ms ./scripts/run_scenario.sh
#   DETECTION_LOCATION=edge SCENARIO=mixed DEVICE_COUNT=5 ./scripts/run_scenario.sh
#
# Zmienne środowiskowe:
#   DETECTION_LOCATION  — edge | central (domyślnie: edge)
#   SCENARIO            — normal | mixed | flood | payload | value (domyślnie: mixed)
#   DURATION            — czas przebiegu w sekundach (domyślnie: 120)
#   LATENCY             — opóźnienie netem dla wariantu central (domyślnie: 60ms)
#   DEVICE_COUNT        — liczba urządzeń IoT (domyślnie: 1)
#   DATA_DIR            — katalog na dane (domyślnie: ./data)
# ---------------------------------------------------------------------------
set -euo pipefail

DATA_DIR="${DATA_DIR:-./data}"
VARIANT="${DETECTION_LOCATION:-edge}"
SCENARIO="${SCENARIO:-mixed}"
DURATION="${DURATION:-120}"
LATENCY="${LATENCY:-60ms}"
DEVICE_COUNT="${DEVICE_COUNT:-1}"

# Walidacja
if [[ "$VARIANT" != "edge" && "$VARIANT" != "central" ]]; then
  echo "BLAD: DETECTION_LOCATION musi byc 'edge' lub 'central' (podano: $VARIANT)" >&2
  exit 1
fi
if [[ ! "$SCENARIO" =~ ^(normal|mixed|flood|payload|value)$ ]]; then
  echo "BLAD: SCENARIO musi byc normal|mixed|flood|payload|value (podano: $SCENARIO)" >&2
  exit 1
fi

cleanup() {
  echo ">> Sprzatanie..."
  [ "$VARIANT" = "central" ] && ./scripts/apply_netem.sh del 2>/dev/null || true
  docker compose down --timeout 10 2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "========================================"
echo "  Przebieg eksperymentalny"
echo "  Wariant:     $VARIANT"
echo "  Scenariusz:  $SCENARIO"
echo "  Czas:        ${DURATION}s"
echo "  Urzadzenia:  $DEVICE_COUNT"
[ "$VARIANT" = "central" ] && echo "  Opoznienie:  $LATENCY"
echo "  Dane:        $DATA_DIR"
echo "========================================"
echo ""

# Przygotowanie katalogu danych
mkdir -p "$DATA_DIR"
rm -f "$DATA_DIR"/ground_truth_*.csv \
      "$DATA_DIR"/detections.csv \
      "$DATA_DIR"/edge_stats.csv \
      "$DATA_DIR"/central_stats.csv \
      "$DATA_DIR"/edge_telemetry.csv \
      "$DATA_DIR"/central_telemetry.csv \
      "$DATA_DIR"/results.json

# Start infrastruktury
echo ">> Uruchamiam broker + edge + central..."
export DATA_DIR DETECTION_LOCATION="$VARIANT" SCENARIO DURATION LATENCY
docker compose up -d --build broker edge central

# Czekaj na gotowość brokera (healthcheck)
echo ">> Czekam na gotowość brokera..."
for i in $(seq 1 30); do
  if docker compose exec broker mosquitto_pub -t test -m ok -q 0 2>/dev/null; then
    echo "   Broker gotowy (${i}s)"
    break
  fi
  sleep 1
done

# Emulacja opóźnienia chmury (tylko wariant central)
if [ "$VARIANT" = "central" ]; then
  echo ">> Nakladam opoznienie netem: $LATENCY"
  ./scripts/apply_netem.sh add "$LATENCY"
fi

# Uruchomienie urządzeń (blokujące — kończy się po DURATION)
echo ">> Uruchamiam $DEVICE_COUNT urzadzen IoT..."
docker compose up --build --scale "device=$DEVICE_COUNT" device

# Daj czas na dojście ostatnich wiadomości
sleep 2

# Graceful stop (SIGTERM → flush CSV)
echo ">> Zatrzymuję edge i central..."
docker compose stop --timeout 10 edge central

echo ""
echo ">> Przebieg zakonczony."
echo "   Analiza: DATA_DIR=$DATA_DIR VARIANT=$VARIANT python analyze/analyze.py"
echo ""
