#!/usr/bin/env bash
# LEGACY/NIEUZYWANE: opoznienie chmury emulujemy teraz toxiproxy (kierunkowo,
# broker->central), bo `tc netem` na root qdisc dziala tylko na egress i nie
# dodawal opoznienia na sciezce telemetrii (broker->central). Patrz run.py
# (init_toxiproxy) oraz docker-compose.latency.yml. Plik zachowany pomocniczo.
#
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
