#!/usr/bin/env bash
# Jeden przebieg jednego scenariusza — cienki delegat do run.py
# (poprawny cykl zycia kontenerow, toxiproxy dla wariantu central).
#   DETECTION_LOCATION=edge SCENARIO=mixed DURATION=120 ./scripts/run_scenario.sh
#   DETECTION_LOCATION=central SCENARIO=mixed DURATION=120 LATENCY=60ms ./scripts/run_scenario.sh
set -e
LOC="${DETECTION_LOCATION:-edge}"; SC="${SCENARIO:-mixed}"
DUR="${DURATION:-120}"; DEV="${DEVICE_COUNT:-1}"; LATENCY="${LATENCY:-60ms}"
case "$LATENCY" in *ms) LAT="$LATENCY" ;; *) LAT="${LATENCY}ms" ;; esac
PYTHON="${PYTHON:-python}"; command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3
"$PYTHON" run.py scenario "$LOC" "$SC" --duration "$DUR" --devices "$DEV" --latency "$LAT"
