#!/usr/bin/env bash
# Pomocniczy przebieg jednego scenariusza. Przyklad:
#   DETECTION_LOCATION=edge SCENARIO=flood DURATION=120 ./scripts/run_scenario.sh
set -e
VARIANT="${DETECTION_LOCATION:-edge}"
echo ">> Czyszcze data/ i startuje stack (wariant=$VARIANT, scenariusz=${SCENARIO:-mixed})"
mkdir -p data && rm -f data/ground_truth_*.csv data/detections.csv data/edge_stats.csv
docker compose up -d --build broker edge central
sleep 3
[ "$VARIANT" = "central" ] && ./scripts/apply_netem.sh add "${LATENCY:-60ms}" || true
( ./scripts/collect_stats.sh iot-edge 0.5 ./data/edge_stats.csv & echo $! > /tmp/stats.pid )
docker compose up --build device          # uruchamia symulator do DURATION i konczy
kill "$(cat /tmp/stats.pid)" 2>/dev/null || true
[ "$VARIANT" = "central" ] && ./scripts/apply_netem.sh del || true
echo ">> Gotowe. Analiza:"
echo "   DATA_DIR=./data VARIANT=$VARIANT python analyze/analyze.py"
