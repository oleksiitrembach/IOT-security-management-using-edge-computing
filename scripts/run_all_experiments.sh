#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_all_experiments.sh — MASTER SKRYPT
# ---------------------------------------------------------------------------
# Uruchamia WSZYSTKIE scenariusze × warianty × N powtórzeń.
# Jedno polecenie: ./scripts/run_all_experiments.sh
#
# Szacowany czas (RUNS=30, DURATION=120s, 5 scenariuszy × 2 warianty):
#   ~300 przebiegów × ~2.5 min ≈ 12.5 godzin (uruchom overnight)
#
# Szybki test (RUNS=3, DURATION=30):
#   RUNS=3 DURATION=30 ./scripts/run_all_experiments.sh
# ---------------------------------------------------------------------------
set -euo pipefail

RUNS="${RUNS:-30}"
DURATION="${DURATION:-120}"
LATENCY="${LATENCY:-60ms}"
DEVICE_COUNT_DEFAULT="${DEVICE_COUNT:-1}"
DEVICE_COUNT_SCALE="${DEVICE_COUNT_SCALE:-5}"  # dla S6

SCENARIOS=("normal" "mixed" "flood" "payload" "value")
LOCATIONS=("edge" "central")

STARTED=$(date +%s)
TOTAL_BATCHES=$(( ${#SCENARIOS[@]} * ${#LOCATIONS[@]} ))
BATCH_NUM=0

echo ""
echo "================================================================"
echo "  PEŁNY CYKL EKSPERYMENTALNY"
echo "  Scenariusze: ${SCENARIOS[*]}"
echo "  Warianty:    ${LOCATIONS[*]}"
echo "  Powtorzenia: $RUNS per batch"
echo "  Czas/run:    ${DURATION}s"
echo "  Batche:      $TOTAL_BATCHES"
echo "  Szac. czas:  ~$(( TOTAL_BATCHES * RUNS * (DURATION + 30) / 3600 )) h"
echo "================================================================"
echo ""

for SCENARIO in "${SCENARIOS[@]}"; do
  for LOCATION in "${LOCATIONS[@]}"; do
    BATCH_NUM=$((BATCH_NUM + 1))
    ELAPSED=$(( $(date +%s) - STARTED ))

    echo ""
    echo "################################################################"
    echo "  BATCH $BATCH_NUM/$TOTAL_BATCHES: $LOCATION × $SCENARIO"
    [ "$BATCH_NUM" -gt 1 ] && echo "  Czas dotychczas: $((ELAPSED/60)) min"
    echo "################################################################"
    echo ""

    ./scripts/run_batch.sh "$LOCATION" "$SCENARIO" "$RUNS" "$LATENCY" "$DURATION" "$DEVICE_COUNT_DEFAULT"
  done
done

# S6: Skalowalnośc — dodatkowe runy z większą liczbą urządzeń
echo ""
echo "################################################################"
echo "  BONUS: SKALOWALNOŚC (S6) — $DEVICE_COUNT_SCALE urządzeń"
echo "################################################################"
echo ""

for LOCATION in "${LOCATIONS[@]}"; do
  BATCH_NUM=$((BATCH_NUM + 1))
  ./scripts/run_batch.sh "$LOCATION" "mixed" "$RUNS" "$LATENCY" "$DURATION" "$DEVICE_COUNT_SCALE"
done

TOTAL_TIME=$(( $(date +%s) - STARTED ))

echo ""
echo "================================================================"
echo "  CAŁY CYKL ZAKOŃCZONY"
echo "  Czas calkowity: $((TOTAL_TIME / 3600))h $((TOTAL_TIME % 3600 / 60))m"
echo "================================================================"
echo ""

# Finalna agregacja wszystkich wyników
echo ">> Finalna agregacja..."
python analyze/aggregate.py --data-root ./data

echo ""
echo "Gotowe. Wyniki w ./data/aggregate_results.json"
echo "Wykresy w ./data/fig_*.png"
echo ""
echo "Nastepny krok: wklej wyniki do rozdzialu 7 pracy."
