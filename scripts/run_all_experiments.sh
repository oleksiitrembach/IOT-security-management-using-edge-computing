#!/usr/bin/env bash
# Pelny cykl bazowy (5 scenariuszy x 2 warianty x N powtorzen) — delegat do run.py.
# Rozszerzone serie (PB1/PB5/S7/S6): ./scripts/run_extended_scenarios.sh
#   RUNS=30 DURATION=120 ./scripts/run_all_experiments.sh
set -e
RUNS="${RUNS:-30}"; DUR="${DURATION:-120}"
PYTHON="${PYTHON:-python}"; command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3
"$PYTHON" run.py all --runs "$RUNS" --duration "$DUR"
