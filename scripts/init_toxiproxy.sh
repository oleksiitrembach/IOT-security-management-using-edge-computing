#!/usr/bin/env bash
# Tworzy proxy broker_proxy (toxiproxy:1883 -> broker:1883) i dodaje opoznienie
# downstream (broker -> central) o LAT ms. Uzywa stabilnego API HTTP.
#   ./scripts/init_toxiproxy.sh 60
set -e
LAT="${1:-60}"
API="http://localhost:8474"
echo ">> Tworze proxy broker_proxy z opoznieniem ${LAT} ms (downstream)"
# usun istniejace (idempotentnie)
curl -s -X DELETE "$API/proxies/broker_proxy" >/dev/null 2>&1 || true
curl -s -X POST "$API/proxies" \
  -d "{\"name\":\"broker_proxy\",\"listen\":\"0.0.0.0:1883\",\"upstream\":\"broker:1883\",\"enabled\":true}" >/dev/null
curl -s -X POST "$API/proxies/broker_proxy/toxics" \
  -d "{\"name\":\"lat_down\",\"type\":\"latency\",\"stream\":\"downstream\",\"attributes\":{\"latency\":${LAT},\"jitter\":0}}" >/dev/null
echo ">> Stan proxy:"
curl -s "$API/proxies/broker_proxy"
echo
# Alternatywa CLI (jesli wolisz):
#   docker exec iot-toxiproxy /toxiproxy-cli create broker_proxy --listen 0.0.0.0:1883 --upstream broker:1883
#   docker exec iot-toxiproxy /toxiproxy-cli toxic add broker_proxy --type latency --attribute latency=${LAT}
