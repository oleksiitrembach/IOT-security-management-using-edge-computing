#!/usr/bin/env bash
# PB5 — skalowalnosc. Cienki delegat do run.py (poprawny cykl zycia kontenerow).
#   RUNS=10 DURATION=120 COUNTS="1 5 10 20" ./scripts/run_scalability.sh
set -e
RUNS="${RUNS:-10}"; DURATION="${DURATION:-120}"; COUNTS="${COUNTS:-1 5 10 20}"
PYTHON="${PYTHON:-python}"; command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3
"$PYTHON" run.py scalability --runs "$RUNS" --duration "$DURATION" --counts $COUNTS
