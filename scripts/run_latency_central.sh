#!/usr/bin/env bash
# CZYSTY PB1 dla wariantu scentralizowanego (S2-S5) przez toxiproxy.
# Wynik: data/runs/central_<scenario>_<i>/  -> agregacja na koncu.
#   RUNS=30 DURATION=120 LATENCY=60 ./scripts/run_latency_central.sh
set -e
RUNS="${RUNS:-30}"; DURATION="${DURATION:-120}"; LATENCY="${LATENCY:-60}"
SCENARIOS="${SCENARIOS:-mixed flood payload value}"
DC="docker compose -f docker-compose.yml -f docker-compose.latency.yml"

DETECTION_LOCATION=central $DC up -d --build broker toxiproxy edge central
sleep 4
./scripts/init_toxiproxy.sh "$LATENCY"

for sc in $SCENARIOS; do
  for i in $(seq 1 "$RUNS"); do
    echo ">> central / $sc / run $i"
    rm -f data/*.csv
    SCENARIO="$sc" DURATION="$DURATION" $DC run --rm device
    mkdir -p "data/runs/central_${sc}_${i}"
    mv data/*.csv "data/runs/central_${sc}_${i}/" 2>/dev/null || true
  done
done
$DC down
python analyze/aggregate_runs.py --data-root ./data/runs --filter central_
