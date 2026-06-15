#!/usr/bin/env bash
# S7 — awaria i przywrocenie wezla brzegowego. Cienki delegat do run.py.
#   DURATION=180 KILL_AT=60 DOWN=30 ./scripts/run_failure.sh
set -e
DURATION="${DURATION:-180}"; KILL_AT="${KILL_AT:-60}"; DOWN="${DOWN:-30}"
PYTHON="${PYTHON:-python}"; command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python3
"$PYTHON" run.py failure --duration "$DURATION" --kill-at "$KILL_AT" --down "$DOWN"
