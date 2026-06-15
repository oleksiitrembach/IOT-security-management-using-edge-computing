#!/usr/bin/env bash
# Czysty czas detekcji wariantu scentralizowanego (PB1) — toxiproxy.
# Cienki delegat do run.py (jedno, poprawne zrodlo prawdy, cross-platform):
#   RUNS=30 DURATION=120 LATENCY=60 ./scripts/run_latency_central.sh
set -e
RUNS="${RUNS:-30}"; DURATION="${DURATION:-120}"; LATENCY="${LATENCY:-60}"
SCENARIOS="${SCENARIOS:-mixed flood payload value}"
case "$LATENCY" in *ms) LAT="$LATENCY" ;; *) LAT="${LATENCY}ms" ;; esac
PYTHON="${PYTHON:-python}"; command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3

for sc in $SCENARIOS; do
  "$PYTHON" run.py batch central "$sc" "$RUNS" --duration "$DURATION" --latency "$LAT"
done
"$PYTHON" analyze/aggregate.py --data-root ./data \
  --scenarios $SCENARIOS --locations central
