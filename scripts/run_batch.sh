#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_batch.sh — seria powtórzeń jednego scenariusza × wariantu
# ---------------------------------------------------------------------------
# Przykład:
#   ./scripts/run_batch.sh edge mixed 30 60ms 120 1
#   ./scripts/run_batch.sh central flood 30 60ms 120 1
#   ./scripts/run_batch.sh edge mixed 30 60ms 120 5    # 5 urządzeń (S6/PB5)
#
# Argumenty:
#   $1 — edge | central
#   $2 — scenario (normal|mixed|flood|payload|value)
#   $3 — liczba powtórzeń (≥30)
#   $4 — latency dla central (domyślnie: 60ms)
#   $5 — duration w sekundach (domyślnie: 120)
#   $6 — device_count (domyślnie: 1)
# ---------------------------------------------------------------------------
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "Uzycie: $0 <edge|central> <scenario> <runs> [latency] [duration] [device_count]"
  echo ""
  echo "Przyklad: $0 edge mixed 30 60ms 120 1"
  exit 1
fi

LOCATION="$1"
SCENARIO="$2"
RUNS="$3"
LATENCY="${4:-60ms}"
DURATION="${5:-120}"
DEVICE_COUNT="${6:-1}"
DATA_ROOT="./data"

if [[ "$LOCATION" != "edge" && "$LOCATION" != "central" ]]; then
  echo "BLAD: Pierwszy argument musi byc 'edge' lub 'central'" >&2
  exit 1
fi

STARTED=$(date +%s)
echo ""
echo "================================================================"
echo "  SERIA EKSPERYMENTALNA"
echo "  Wariant:     $LOCATION"
echo "  Scenariusz:  $SCENARIO"
echo "  Powtorzenia: $RUNS"
echo "  Czas/run:    ${DURATION}s"
echo "  Urzadzenia:  $DEVICE_COUNT"
[ "$LOCATION" = "central" ] && echo "  Opoznienie:  $LATENCY"
echo "  Szac. czas:  ~$(( RUNS * (DURATION + 30) / 60 )) min"
echo "================================================================"
echo ""

FAILED=0

for i in $(seq 1 "$RUNS"); do
  RUN_DIR="$DATA_ROOT/${LOCATION}_${SCENARIO}_run$(printf '%02d' "$i")"
  ELAPSED=$(( $(date +%s) - STARTED ))
  if [ "$i" -gt 1 ]; then
    ETA=$(( ELAPSED * (RUNS - i + 1) / (i - 1) ))
    ETA_MIN=$(( ETA / 60 ))
  else
    ETA_MIN="?"
  fi

  echo ""
  echo ">> Run #${i}/${RUNS} [ETA: ~${ETA_MIN} min]"
  echo "   Katalog: $RUN_DIR"
  mkdir -p "$RUN_DIR"
  rm -rf "${RUN_DIR:?}"/*

  if DATA_DIR="$RUN_DIR" \
     DETECTION_LOCATION="$LOCATION" \
     SCENARIO="$SCENARIO" \
     DURATION="$DURATION" \
     LATENCY="$LATENCY" \
     DEVICE_COUNT="$DEVICE_COUNT" \
     ./scripts/run_scenario.sh; then

    # Analiza po zakończeniu runu
    DATA_DIR="$RUN_DIR" VARIANT="$LOCATION" python analyze/analyze.py \
      && echo "   Analiza OK: $RUN_DIR/results.json" \
      || echo "   UWAGA: Analiza nie powiodla sie dla runu #$i"
  else
    echo "   BLAD: Run #$i nie powiodl sie!" >&2
    FAILED=$((FAILED + 1))
  fi

  # Krótka pauza między runami
  sleep 3
done

TOTAL_TIME=$(( $(date +%s) - STARTED ))
echo ""
echo "================================================================"
echo "  SERIA ZAKONCZONA"
echo "  Ukonczono: $((RUNS - FAILED))/$RUNS"
echo "  Bledne:    $FAILED"
echo "  Czas:      $((TOTAL_TIME / 60)) min $((TOTAL_TIME % 60)) s"
echo "================================================================"
echo ""

if [ "$FAILED" -gt 0 ]; then
  echo "UWAGA: $FAILED runow zakonczylo sie bledem!" >&2
fi

# Agregacja wyników
echo ">> Uruchamiam agregacje..."
python analyze/aggregate.py \
  --data-root "$DATA_ROOT" \
  --scenarios "$SCENARIO" \
  --locations "$LOCATION" \
  && echo "   Agregacja OK" \
  || echo "   UWAGA: Agregacja nie powiodla sie"

echo ""
echo "Dane w katalogach:"
ls -1d "$DATA_ROOT/${LOCATION}_${SCENARIO}_run"* 2>/dev/null || echo "  (brak)"
