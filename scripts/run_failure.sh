#!/usr/bin/env bash
# S7 - awaria i przywrocenie wezla brzegowego (edge variant, mixed).
# Zabija kontener edge w trakcie przebiegu i restartuje po DOWN sekundach.
#   DURATION=180 KILL_AT=60 DOWN=30 ./scripts/run_failure.sh
set -e
DURATION="${DURATION:-180}"; KILL_AT="${KILL_AT:-60}"; DOWN="${DOWN:-30}"

DETECTION_LOCATION=edge docker compose up -d --build broker edge central
sleep 4
rm -f data/*.csv
echo ">> start urzadzenia (mixed), DURATION=$DURATION"
SCENARIO=mixed DURATION="$DURATION" docker compose up -d --no-deps --scale device=1 device

sleep "$KILL_AT"
T_KILL=$(date +%s.%N); docker kill iot-edge >/dev/null; echo ">> EDGE ubity @ $T_KILL"
sleep "$DOWN"
docker start iot-edge >/dev/null; T_UP=$(date +%s.%N); echo ">> EDGE wznowiony @ $T_UP"
echo "t_kill,t_up" > data/failure_window.csv
echo "$T_KILL,$T_UP" >> data/failure_window.csv

# poczekaj na zakonczenie urzadzenia
sleep $((DURATION - KILL_AT - DOWN + 8))
docker compose down
python analyze/analyze_failure.py --data-dir ./data
