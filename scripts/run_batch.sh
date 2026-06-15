#!/usr/bin/env bash
# Seria powtorzen jednego scenariusza x wariantu — cienki delegat do run.py.
#   ./scripts/run_batch.sh edge mixed 30
#   ./scripts/run_batch.sh central mixed 30 60ms 120 1
set -e
if [ "$#" -lt 3 ]; then
  echo "Uzycie: $0 <edge|central> <scenario> <runs> [latency] [duration] [devices]"
  exit 1
fi
LOC="$1"; SC="$2"; RUNS="$3"; LATENCY="${4:-60ms}"; DUR="${5:-120}"; DEV="${6:-1}"
case "$LATENCY" in *ms) LAT="$LATENCY" ;; *) LAT="${LATENCY}ms" ;; esac
PYTHON="${PYTHON:-python}"; command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3
"$PYTHON" run.py batch "$LOC" "$SC" "$RUNS" --duration "$DUR" --devices "$DEV" --latency "$LAT"
