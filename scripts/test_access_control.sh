#!/usr/bin/env bash
# PB4 / S6 - kontrola dostepu. Wymaga overlay TLS+ACL (docker-compose.tls.yml)
# oraz wczesniej wygenerowanych certyfikatow (./scripts/gen_certs.sh).
# Skrypt PROBUJE wykonac niedozwolone operacje i sprawdza, czy broker je ODRZUCA.
# UWAGA: dostosuj nazwy uzytkownikow/tematow/certow do swojej konfiguracji ACL.
set -e
NET="${NET:-iot-edge-testbed_default}"
HOST="${BROKER:-broker}"; PORT="${PORT:-8883}"
CAFILE="${CAFILE:-/mosquitto/certs/ca.crt}"
echo ">> Test 1: publikacja na cudzy temat (oczekiwane: ODRZUCENIE)"
if docker run --rm --network "$NET" -v "$(pwd)/mosquitto/certs:/mosquitto/certs:ro" \
     eclipse-mosquitto mosquitto_pub -h "$HOST" -p "$PORT" --cafile "$CAFILE" \
     -t "iot/INNE-URZADZENIE/telemetry" -m "spoof" -u dev-01 -P wrongpass 2>/dev/null; then
  echo "   FAIL: publikacja przeszla (brak kontroli dostepu)"
else
  echo "   PASS: publikacja odrzucona"
fi
echo ">> Test 2: subskrypcja tematu alertow bez uprawnien (oczekiwane: ODRZUCENIE)"
if timeout 5 docker run --rm --network "$NET" -v "$(pwd)/mosquitto/certs:/mosquitto/certs:ro" \
     eclipse-mosquitto mosquitto_sub -h "$HOST" -p "$PORT" --cafile "$CAFILE" \
     -t "alerts" -C 1 -u dev-01 -P wrongpass 2>/dev/null; then
  echo "   FAIL: subskrypcja przeszla"
else
  echo "   PASS: subskrypcja odrzucona"
fi
echo ">> Zapisz wynik (PASS/FAIL) recznie do tabeli S6 w pracy."
