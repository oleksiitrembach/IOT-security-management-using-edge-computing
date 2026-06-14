#!/usr/bin/env bash
# Naklada/zdejmuje opoznienie sieciowe na kontenerze centralnym (emulacja chmury).
# Wlacz PRZED przebiegiem wariantu scentralizowanego:
#   ./scripts/apply_netem.sh add 60ms
# Wylacz po przebiegu:
#   ./scripts/apply_netem.sh del
ACTION="${1:-add}"
DELAY="${2:-60ms}"
CONTAINER="${3:-iot-central}"
IFACE="${4:-eth0}"
if [ "$ACTION" = "add" ]; then
  docker exec "$CONTAINER" tc qdisc add dev "$IFACE" root netem delay "$DELAY" \
    && echo "Dodano opoznienie $DELAY na $CONTAINER/$IFACE"
else
  docker exec "$CONTAINER" tc qdisc del dev "$IFACE" root 2>/dev/null \
    && echo "Usunieto opoznienie z $CONTAINER/$IFACE"
fi
