#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# gen_certs.sh — generuje certyfikaty CA + serwer + klient do scenariusza S5
# ---------------------------------------------------------------------------
# Użycie: ./scripts/gen_certs.sh
# Wynik:  certs/ z plikami CA, serwera i klienta
# ---------------------------------------------------------------------------
set -euo pipefail

CERT_DIR="./certs"
DAYS=365
SUBJ_CA="/CN=IoT-Testbed-CA"
SUBJ_SERVER="/CN=iot-broker"
SUBJ_CLIENT="/CN=iot-client"

echo ">> Generowanie certyfikatow TLS do scenariusza S5..."
mkdir -p "$CERT_DIR"

# CA (Certificate Authority)
echo "   [1/3] CA..."
openssl genrsa -out "$CERT_DIR/ca.key" 2048 2>/dev/null
openssl req -new -x509 -days $DAYS -key "$CERT_DIR/ca.key" \
  -out "$CERT_DIR/ca.crt" -subj "$SUBJ_CA" 2>/dev/null

# Certyfikat serwera (broker Mosquitto)
echo "   [2/3] Serwer (broker)..."
openssl genrsa -out "$CERT_DIR/server.key" 2048 2>/dev/null
openssl req -new -key "$CERT_DIR/server.key" \
  -out "$CERT_DIR/server.csr" -subj "$SUBJ_SERVER" 2>/dev/null
openssl x509 -req -days $DAYS \
  -in "$CERT_DIR/server.csr" \
  -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
  -CAcreateserial \
  -out "$CERT_DIR/server.crt" 2>/dev/null

# Certyfikat klienta (edge/central/device)
echo "   [3/3] Klient..."
openssl genrsa -out "$CERT_DIR/client.key" 2048 2>/dev/null
openssl req -new -key "$CERT_DIR/client.key" \
  -out "$CERT_DIR/client.csr" -subj "$SUBJ_CLIENT" 2>/dev/null
openssl x509 -req -days $DAYS \
  -in "$CERT_DIR/client.csr" \
  -CA "$CERT_DIR/ca.crt" -CAkey "$CERT_DIR/ca.key" \
  -CAcreateserial \
  -out "$CERT_DIR/client.crt" 2>/dev/null

# Hasło dla Mosquitto (edge-node i central jako użytkownicy)
echo "   Generowanie pliku hasel Mosquitto..."
docker run --rm -v "$(pwd)/$CERT_DIR:/certs" eclipse-mosquitto:2 \
  mosquitto_passwd -b -c /certs/passwd edge-node edgepass 2>/dev/null || \
  echo "   (Mosquitto passwd wymaga uruchomionego Dockera — pominięto)"

docker run --rm -v "$(pwd)/$CERT_DIR:/certs" eclipse-mosquitto:2 \
  mosquitto_passwd -b /certs/passwd central centralpass 2>/dev/null || true

docker run --rm -v "$(pwd)/$CERT_DIR:/certs" eclipse-mosquitto:2 \
  mosquitto_passwd -b /certs/passwd device devicepass 2>/dev/null || true

# Sprzątanie CSR
rm -f "$CERT_DIR"/*.csr "$CERT_DIR"/*.srl

echo ""
echo ">> Certyfikaty wygenerowane w $CERT_DIR/"
ls -la "$CERT_DIR/"
echo ""
echo "Nastepny krok:"
echo "  docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d"
