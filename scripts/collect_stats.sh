#!/usr/bin/env bash
# Zbiera CPU% i RAM kontenera wezla brzegowego co INTERVAL sekund.
# Uruchom na HOSCIE rownolegle z przebiegiem urzadzenia:
#   ./scripts/collect_stats.sh iot-edge 0.5 ./data/edge_stats.csv
# UWAGA: edge_node.py i central.py używają psutil wewnętrznie, co jest precyzyjniejsze.
# Ten skrypt pozostaje jako backup (np. dla monitorowania brokera).
CONTAINER="${1:-iot-edge}"
INTERVAL="${2:-0.5}"
OUT="${3:-./data/edge_stats.csv}"
echo "ts,cpu_perc,mem_mb" > "$OUT"
echo "Zbieram statystyki z $CONTAINER -> $OUT (Ctrl+C aby zakonczyc)"
while true; do
  line=$(docker stats --no-stream --format '{{.CPUPerc}};{{.MemUsage}}' "$CONTAINER" 2>/dev/null)
  if [ -n "$line" ]; then
    cpu=$(echo "$line" | cut -d';' -f1 | tr -d '% ')
    memraw=$(echo "$line" | cut -d';' -f2 | awk '{print $1}')
    num=$(echo "$memraw" | sed 's/[A-Za-z]*//g')
    unit=$(echo "$memraw" | sed 's/[0-9.]*//g')
    case "$unit" in
      GiB) mem=$(awk "BEGIN{print $num*1024}") ;;
      KiB) mem=$(awk "BEGIN{print $num/1024}") ;;
      *)   mem=$num ;;
    esac
    echo "$(date +%s.%N),$cpu,$mem" >> "$OUT"
  fi
  sleep "$INTERVAL"
done
