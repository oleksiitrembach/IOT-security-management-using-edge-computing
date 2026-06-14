# Testbed: bezpieczenstwo sieci IoT z przetwarzaniem brzegowym (edge)

Odtwarzalne srodowisko do pracy magisterskiej. Cala architektura jako kontenery
Docker: broker MQTT (Mosquitto), wezel brzegowy z limitem zasobow (emulacja
ograniczonego urzadzenia), system centralny oraz skalowalne symulatory urzadzen
IoT. Pozwala zmierzyc metryki rozdzialu 7 BEZ zadnego sprzetu fizycznego.

## Wymagania
- Docker + Docker Compose v2 (`docker compose version`)
- Python 3 na hoscie do analizy: `pip install -r analyze/requirements-analyze.txt`

## Architektura (mapuje na rozdz. 4 pracy)
    device(y)  --MQTT-->  broker(Mosquitto)  -->  edge (detekcja, tryb edge)
                                              -->  central (detekcja, tryb central + netem)
- Wariant **brzegowy**: detekcja na `edge` (lokalnie, bez opoznienia).
- Wariant **scentralizowany**: detekcja na `central`, obciazonym opoznieniem
  sieciowym (netem) odwzorowujacym droge do chmury.
Roznica = wplyw lokalizacji przetwarzania na czas detekcji (PB1/H1).

## Szybki start (wariant brzegowy, scenariusz mieszany)
    DETECTION_LOCATION=edge SCENARIO=mixed DURATION=120 ./scripts/run_scenario.sh
    DATA_DIR=./data VARIANT=brzegowy python analyze/analyze.py

## Wariant scentralizowany (z emulacja opoznienia chmury)
    DETECTION_LOCATION=central SCENARIO=mixed DURATION=120 LATENCY=60ms ./scripts/run_scenario.sh
    DATA_DIR=./data VARIANT=scentralizowany python analyze/analyze.py

## Reczne uruchomienie (bez skryptu pomocniczego)
    # 1. start brokera + wezlow
    DETECTION_LOCATION=edge docker compose up -d --build broker edge central
    # 2. (tylko central) opoznienie:  ./scripts/apply_netem.sh add 60ms
    # 3. zbieranie zasobow w tle (host):  ./scripts/collect_stats.sh iot-edge 0.5 ./data/edge_stats.csv
    # 4. uruchom urzadzenia (konczy sie po DURATION):
    SCENARIO=flood DURATION=120 docker compose up --build device
    # 5. zatrzymaj zbieranie (Ctrl+C), potem analiza:
    DATA_DIR=./data VARIANT=brzegowy python analyze/analyze.py
    # 6. sprzatanie:  docker compose down

## Skalowanie liczby urzadzen (PB5 - skalowalnosc)
    SCENARIO=mixed docker compose up --build --scale device=10 device
(kazda replika to osobne urzadzenie - DEVICE_ID z nazwy hosta)

## Mapowanie scenariuszy (Tabela 3 w pracy)
| SCENARIO | Scenariusz | Bada |
|----------|-----------|------|
| normal   | S1 ruch normalny           | FPR, zasoby |
| mixed    | S2 zwiekszone obciazenie   | skalowalnosc, zasoby |
| flood    | S3 nadmierna czestotliwosc | czas detekcji, czulosc |
| payload  | S4 anomalia ladunku        | czas detekcji, precyzja |
| value    | (anomalia wartosci)        | czulosc reguly statystycznej |

## Co dostajesz (do rozdzialu 7)
- `data/detections.csv` + `data/ground_truth_*.csv` -> Tabele 4 i 5
- `data/edge_stats.csv` -> Tabela 6
- `data/detection_time_*.png` -> Rysunek 4
Skrypt `analyze/analyze.py` wypisuje gotowe liczby do tabel.

## Parametry (zmienne srodowiskowe)
RATE, DURATION, ANOMALY_RATE, FLOOD_BURST, PAYLOAD_BYTES, MU, SIGMA,
FREQ_THRESHOLD, MAX_PAYLOAD, WARMUP, K_SIGMA, LATENCY, DETECTION_LOCATION, SCENARIO.

## Metodyka (rozdz. 6)
- n >= 30 powtorzen na scenariusz/wariant (powtorz przebieg i agreguj).
- Wszystkie kontenery na jednym hoscie -> wspolny zegar, brak potrzeby NTP.
- Opoznienie do chmury: `tc netem` na kontenerze central (limitacja: emulacja, nie realna s
  siec WAN - opisz w 7.5).
- Bezpieczenstwo (S5): wlacz auth/ACL/TLS w mosquitto.conf (patrz acl.example).

## Uwaga o rzetelnosci
Wyniki w rozdziale 7 pracy wypelniaj WYLACZNIE liczbami z tych przebiegow.
Commituj kod i pliki data/ jako dowod autorstwa.
