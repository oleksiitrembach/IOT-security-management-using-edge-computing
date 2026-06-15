#!/usr/bin/env bash
# Rozszerzone scenariusze badawcze (PB1, PB5, S7, PB4/S6) — jedna sekwencja.
# Cienki delegat do run.py (poprawny cykl zycia kontenerow, cross-platform).
#   RUNS_PB1=30 RUNS_SCALE=10 DURATION=120 ./scripts/run_extended_scenarios.sh
set -e
echo "=========================================="
echo " Rozszerzone scenariusze badawcze (PB1, PB4, PB5, S7)"
echo "=========================================="
date
RUNS_PB1="${RUNS_PB1:-30}"; RUNS_SCALE="${RUNS_SCALE:-10}"; DURATION="${DURATION:-120}"
PYTHON="${PYTHON:-python}"; command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3
"$PYTHON" run.py extended --runs-pb1 "$RUNS_PB1" --runs-scale "$RUNS_SCALE" \
  --duration "$DURATION" | tee ./data/extended_output.txt
echo "=========================================="
echo " Zakonczono."
echo "=========================================="
date
