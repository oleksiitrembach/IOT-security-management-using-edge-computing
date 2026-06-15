#!/usr/bin/env bash
# PB5 - skalowalnosc: przebiegi edge/mixed dla rosnacej liczby urzadzen.
# Wynik: data/runs/scale_<N>_<i>/  -> tabela N | czas | CPU | RAM | przepustowosc
#   RUNS=10 DURATION=120 COUNTS="1 5 10 20" ./scripts/run_scalability.sh
set -e
RUNS="${RUNS:-10}"; DURATION="${DURATION:-120}"; COUNTS="${COUNTS:-1 5 10 20}"

DETECTION_LOCATION=edge docker compose up -d --build broker edge central
sleep 4
for n in $COUNTS; do
  for i in $(seq 1 "$RUNS"); do
    echo ">> scale=$n / run $i"
    rm -f data/*.csv
    ( ./scripts/collect_stats.sh iot-edge 0.5 ./data/edge_stats.csv & echo $! > /tmp/st.pid )
    SCENARIO=mixed DURATION="$DURATION" docker compose up --build --no-deps --scale device="$n" device
    kill "$(cat /tmp/st.pid)" 2>/dev/null || true
    mkdir -p "data/runs/scale_${n}_${i}"
    mv data/*.csv "data/runs/scale_${n}_${i}/" 2>/dev/null || true
  done
done
docker compose down
python analyze/analyze_scalability.py --data-root ./data/runs --duration "$DURATION"
