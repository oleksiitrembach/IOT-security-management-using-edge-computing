#!/usr/bin/env bash
set -e
echo "=========================================="
echo " Uruchamianie rozszerzonych scenariuszy badawczych (PB1, PB4, PB5, S7)"
echo "=========================================="
date

echo ""
echo "[1/4] PB1: Scentralizowany z toxiproxy"
RUNS=30 DURATION=120 LATENCY=60 ./scripts/run_latency_central.sh | tee ./data/pb1_central_output.txt

echo ""
echo "[2/4] PB5: Skalowalność"
RUNS=10 DURATION=120 COUNTS="1 5 10 20" ./scripts/run_scalability.sh | tee ./data/pb5_scalability_output.txt

echo ""
echo "[3/4] S7: Awaria węzła"
DURATION=180 KILL_AT=60 DOWN=30 ./scripts/run_failure.sh | tee ./data/s7_failure_output.txt

echo ""
echo "[4/4] PB4/S6: Kontrola dostępu"
./scripts/gen_certs.sh >/dev/null 2>&1
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d >/dev/null 2>&1
sleep 5
./scripts/test_access_control.sh | tee ./data/pb4_access_control_output.txt
docker compose down >/dev/null 2>&1

echo ""
echo "=========================================="
echo " Zakończono pomyślnie!"
echo "=========================================="
date
