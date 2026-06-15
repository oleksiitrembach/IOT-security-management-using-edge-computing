"""Cross-platform experiment runner for the IoT Edge Security Testbed.

Single source of truth for every experiment (Windows/Linux/macOS — no bash
required). Every run uses the same correct container lifecycle:

    compose down -> clean data dir -> compose up -d (broker/edge/central
    [+toxiproxy]) -> wait broker -> [central: toxiproxy latency] -> run
    device(s) in foreground -> stop edge+central (SIGTERM flush) -> down

This guarantees the detector's output files (detections.csv, *_stats.csv) are
opened against a clean directory and flushed before they are read — so no
detections are lost.

Commands:
  python run.py scenario <edge|central> <scenario> [--duration N] [--devices N]
  python run.py batch    <edge|central> <scenario> <runs> [--duration N]
  python run.py all      [--runs N] [--duration N]
  python run.py scalability [--runs N] [--duration N] [--counts 1 5 10 20]   # PB5
  python run.py failure     [--duration N] [--kill-at N] [--down N]          # S7
  python run.py access-control                                               # PB4/S6
  python run.py extended    [--runs-pb1 N] [--runs-scale N] [--duration N]   # PB1+PB5+S7+S6
"""

import os
import sys
import time
import json
import shutil
import subprocess
import argparse
import urllib.request

DATA_ROOT = os.path.abspath(os.environ.get("DATA_DIR", "./data"))
SCENARIOS = ["normal", "mixed", "flood", "payload", "value"]
PY = sys.executable


# ---------------------------------------------------------------------------
# Niskopoziomowe helpery
# ---------------------------------------------------------------------------
def run_cmd(cmd, env=None, check=True, capture=False):
    print(f"    > {' '.join(cmd)}")
    return subprocess.run(cmd, env=env, check=check, capture_output=capture)


def compose_cmd(location):
    """Bazowa komenda compose; dla central dokłada overlay z toxiproxy."""
    c = ["docker", "compose", "-f", "docker-compose.yml"]
    if location == "central":
        c += ["-f", "docker-compose.latency.yml"]
    return c


def clean_data(data_dir):
    """Usuwa pliki wynikowe z katalogu PRZED startem kontenerow (klucz: nie
    kasujemy plikow pod dzialajacym detektorem — robimy to przy zatrzymanych)."""
    os.makedirs(data_dir, exist_ok=True)
    for f in ["detections.csv", "edge_stats.csv", "central_stats.csv",
              "edge_telemetry.csv", "central_telemetry.csv", "results.json",
              "failure_window.csv"]:
        p = os.path.join(data_dir, f)
        if os.path.exists(p):
            os.remove(p)
    for p in os.listdir(data_dir):
        if p.startswith("ground_truth_") and p.endswith(".csv"):
            os.remove(os.path.join(data_dir, p))


def wait_broker(dc_cmd, env, tries=30):
    for i in range(tries):
        res = subprocess.run(
            dc_cmd + ["exec", "broker", "mosquitto_pub", "-t", "healthcheck",
                      "-m", "ok", "-q", "0"],
            env=env, capture_output=True)
        if res.returncode == 0:
            print(f"   Broker ready ({i}s)")
            return True
        time.sleep(1)
    print("   WARNING: broker health timeout")
    return False


def init_toxiproxy(latency="60ms", api="http://localhost:8474"):
    """Tworzy proxy broker_proxy (toxiproxy:1883 -> broker:1883) z kierunkowym
    opoznieniem downstream (broker -> central). Uzywa stabilnego API HTTP."""
    lat = int(str(latency).replace("ms", ""))

    def _post(path, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            api + path, data=data, method="POST",
            headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=5).read()

    # Czekaj az API toxiproxy odpowie
    for _ in range(20):
        try:
            urllib.request.urlopen(api + "/version", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    # Usun istniejace (idempotentnie)
    try:
        urllib.request.urlopen(
            urllib.request.Request(api + "/proxies/broker_proxy",
                                   method="DELETE"), timeout=5)
    except Exception:
        pass
    _post("/proxies", {"name": "broker_proxy", "listen": "0.0.0.0:1883",
                       "upstream": "broker:1883", "enabled": True})
    _post("/proxies/broker_proxy/toxics",
          {"name": "lat_down", "type": "latency", "stream": "downstream",
           "attributes": {"latency": lat, "jitter": 0}})
    print(f">> toxiproxy: opoznienie downstream {lat} ms aktywne")


# ---------------------------------------------------------------------------
# Rdzen: jeden poprawny przebieg (bez analizy)
# ---------------------------------------------------------------------------
def lifecycle_run(location, scenario, duration, latency, device_count, data_dir):
    """Jeden przebieg z gwarancja poprawnego cyklu zycia kontenerow.
    Po powrocie w ``data_dir`` sa kompletne, zflushowane CSV (ground_truth,
    detections, *_stats, *_telemetry). NIE uruchamia analizy."""
    env = os.environ.copy()
    env.update({
        "DETECTION_LOCATION": location,
        "SCENARIO": scenario,
        "DURATION": str(duration),
        "LATENCY": latency,
        "DATA_DIR": data_dir,
    })
    dc = compose_cmd(location)

    clean_data(data_dir)
    run_cmd(dc + ["down", "--timeout", "5"], env=env, check=False)

    services = ["broker", "edge", "central"]
    if location == "central":
        services.append("toxiproxy")
    run_cmd(dc + ["up", "-d", "--build"] + services, env=env)
    wait_broker(dc, env)

    if location == "central":
        init_toxiproxy(latency)

    ok = False
    try:
        run_cmd(dc + ["up", "--build", "--no-deps", "--scale",
                      f"device={device_count}", "device"], env=env)
        time.sleep(2)
        # Zatrzymanie (SIGTERM) -> flush detections/stats PRZED odczytem
        run_cmd(dc + ["stop", "--timeout", "10", "edge", "central"], env=env)
        ok = True
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        run_cmd(dc + ["down", "--timeout", "5"], env=env, check=False)
    return ok


# ---------------------------------------------------------------------------
# scenario / batch / all
# ---------------------------------------------------------------------------
def run_scenario(location, scenario, duration=120, latency="60ms",
                 device_count=1, data_dir=DATA_ROOT, analyze=True):
    print(f"\n{'='*46}")
    print(f"  RUN  loc={location}  scenario={scenario}  "
          f"dur={duration}s  devices={device_count}"
          + (f"  latency={latency}" if location == "central" else ""))
    print(f"  data={data_dir}")
    print(f"{'='*46}")
    ok = lifecycle_run(location, scenario, duration, latency,
                       device_count, data_dir)
    if ok and analyze:
        env = os.environ.copy()
        env["DATA_DIR"] = data_dir
        env["VARIANT"] = location
        run_cmd([PY, "analyze/analyze.py"], env=env, check=False)
    return ok


def run_batch(location, scenario, runs, duration=120, latency="60ms",
              device_count=1):
    print(f"\n{'='*60}\n  BATCH: {location} x {scenario} "
          f"({runs} runow, {duration}s)\n{'='*60}")
    failed = 0
    for i in range(1, runs + 1):
        run_dir = os.path.join(DATA_ROOT, f"{location}_{scenario}_run{i:02d}")
        print(f"\n>> Run #{i}/{runs} [{run_dir}]")
        if os.path.exists(run_dir):
            shutil.rmtree(run_dir)
        os.makedirs(run_dir, exist_ok=True)
        if not run_scenario(location, scenario, duration, latency,
                            device_count, data_dir=run_dir):
            failed += 1
            print(f"   WARNING: run #{i} nieudany")
        time.sleep(3)
    print(f"\n>> Batch zakonczony: {runs - failed}/{runs} OK")
    run_cmd([PY, "analyze/aggregate.py", "--data-root", DATA_ROOT,
             "--scenarios", scenario, "--locations", location], check=False)


def run_all(runs=30, duration=120, latency="60ms"):
    for scenario in SCENARIOS:
        for location in ["edge", "central"]:
            run_batch(location, scenario, runs, duration, latency, 1)
    run_cmd([PY, "analyze/aggregate.py", "--data-root", DATA_ROOT], check=False)
    print("\nALL DONE. Zob. data/aggregate_results.json")


# ---------------------------------------------------------------------------
# PB5 — skalowalnosc
# ---------------------------------------------------------------------------
def run_scalability(runs=10, duration=120, counts=(1, 5, 10, 20),
                    latency="60ms"):
    runs_root = os.path.join(DATA_ROOT, "runs")
    os.makedirs(runs_root, exist_ok=True)
    print(f"\n{'='*60}\n  PB5 SKALOWALNOSC  counts={list(counts)}  "
          f"runs={runs}  dur={duration}s\n{'='*60}")
    for n in counts:
        for i in range(1, runs + 1):
            d = os.path.join(runs_root, f"scale_{n}_{i}")
            if os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)
            print(f"\n>> scale={n} run {i}/{runs}")
            # wariant brzegowy, scenariusz mixed (obciazenie 5% anomalii)
            lifecycle_run("edge", "mixed", duration, latency, n, d)
            time.sleep(2)
    run_cmd([PY, "analyze/analyze_scalability.py", "--data-root", runs_root,
             "--duration", str(duration)], check=False)


# ---------------------------------------------------------------------------
# S7 — awaria i przywrocenie wezla brzegowego
# ---------------------------------------------------------------------------
def run_failure(duration=180, kill_at=60, down=30):
    data_dir = os.path.join(DATA_ROOT, "failure")
    env = os.environ.copy()
    env.update({"DETECTION_LOCATION": "edge", "SCENARIO": "mixed",
                "DURATION": str(duration), "DATA_DIR": data_dir})
    dc = compose_cmd("edge")

    print(f"\n{'='*60}\n  S7 AWARIA WEZLA  dur={duration}s  "
          f"kill_at={kill_at}s  down={down}s\n{'='*60}")

    clean_data(data_dir)
    run_cmd(dc + ["down", "--timeout", "5"], env=env, check=False)
    run_cmd(dc + ["up", "-d", "--build", "broker", "edge", "central"], env=env)
    wait_broker(dc, env)
    # Urzadzenie w tle (DURATION kontroluje jego zycie)
    run_cmd(dc + ["up", "-d", "--build", "--no-deps", "--scale", "device=1",
                  "device"], env=env)

    try:
        time.sleep(kill_at)
        t_kill = time.time()
        run_cmd(["docker", "kill", "iot-edge"], check=False)
        print(f">> EDGE ubity @ {t_kill:.3f}")
        time.sleep(down)
        run_cmd(["docker", "start", "iot-edge"], check=False)
        t_up = time.time()
        print(f">> EDGE wznowiony @ {t_up:.3f}")
        with open(os.path.join(data_dir, "failure_window.csv"), "w") as fh:
            fh.write("t_kill,t_up\n")
            fh.write(f"{t_kill:.6f},{t_up:.6f}\n")
        # Doczekaj konca przebiegu urzadzenia
        time.sleep(max(0, duration - kill_at - down + 8))
    finally:
        # detections.csv pisze CENTRAL (nie ubijany) -> flush przy stop
        run_cmd(dc + ["stop", "--timeout", "10", "edge", "central"], env=env,
                check=False)

    run_cmd([PY, "analyze/analyze_failure.py", "--data-dir", data_dir],
            check=False)
    run_cmd(dc + ["down", "--timeout", "5"], env=env, check=False)


# ---------------------------------------------------------------------------
# PB4 / S6 — kontrola dostepu (TLS + ACL)
# ---------------------------------------------------------------------------
def gen_certs():
    """Generuje CA/serwer/klient + plik hasel w ./certs przez kontenery
    (bez openssl/bash na hoscie). Serwer ma CN/SAN = broker (zgodnie z nazwa
    uslugi w sieci compose) — inaczej weryfikacja hosta TLS by zawiodla."""
    cert_dir = os.path.abspath("certs").replace("\\", "/")
    need = ["ca.crt", "server.crt", "server.key", "client.crt", "client.key",
            "passwd"]
    os.makedirs("certs", exist_ok=True)
    if all(os.path.exists(os.path.join("certs", f)) for f in need):
        print(">> certy juz istnieja — pomijam generacje")
    else:
        script = (
            "set -e; cd /certs; "
            "openssl genrsa -out ca.key 2048; "
            "openssl req -new -x509 -days 365 -key ca.key -out ca.crt "
            "-subj /CN=IoT-Testbed-CA; "
            "openssl genrsa -out server.key 2048; "
            "openssl req -new -key server.key -out server.csr -subj /CN=broker; "
            "printf 'subjectAltName=DNS:broker,DNS:localhost' > san.cnf; "
            "openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key "
            "-CAcreateserial -out server.crt -extfile san.cnf; "
            "openssl genrsa -out client.key 2048; "
            "openssl req -new -key client.key -out client.csr -subj /CN=iot-client; "
            "openssl x509 -req -days 365 -in client.csr -CA ca.crt -CAkey ca.key "
            "-CAcreateserial -out client.crt; "
            "rm -f *.csr *.srl san.cnf"
        )
        try:
            run_cmd(["docker", "run", "--rm", "--entrypoint", "sh",
                     "-v", f"{cert_dir}:/certs", "alpine/openssl", "-c", script])
            run_cmd(["docker", "run", "--rm", "-v", f"{cert_dir}:/certs",
                     "eclipse-mosquitto:2", "mosquitto_passwd", "-b", "-c",
                     "/certs/passwd", "edge-node", "edgepass"])
            for u, p in [("central", "centralpass"), ("device", "devicepass")]:
                run_cmd(["docker", "run", "--rm", "-v", f"{cert_dir}:/certs",
                         "eclipse-mosquitto:2", "mosquitto_passwd", "-b",
                         "/certs/passwd", u, p])
        except Exception as e:
            print(f"ERROR: generowanie certow nie powiodlo sie: {e}")
            return False
    # Broker dziala jako user 'mosquitto' — pliki tworzone przez root maja tryb
    # 600 i sa dla niego nieczytelne (crash: "Unable to open pwfile"). Zawsze
    # normalizujemy uprawnienia plikow, ktore czyta broker (testbed: certy
    # jednorazowe, czytelnosc server.key jest tu akceptowalna).
    try:
        run_cmd(["docker", "run", "--rm", "--entrypoint", "sh",
                 "-v", f"{cert_dir}:/certs", "eclipse-mosquitto:2", "-c",
                 "chmod 644 /certs/ca.crt /certs/server.crt /certs/server.key "
                 "/certs/passwd /certs/client.crt 2>/dev/null || true"])
    except Exception:
        pass
    return True


def _mqtt_try(net, args, timeout=8):
    """Uruchamia jednorazowego klienta mosquitto; zwraca returncode
    (0 = operacja przeszla, !=0 = odrzucona)."""
    base = ["docker", "run", "--rm", "--network", net,
            "-v", f"{os.path.abspath('certs').replace(chr(92), '/')}:/certs:ro",
            "eclipse-mosquitto:2"]
    res = subprocess.run(base + args, capture_output=True, timeout=timeout)
    return res.returncode


def run_access_control():
    print(f"\n{'='*60}\n  PB4/S6 KONTROLA DOSTEPU (TLS + ACL)\n{'='*60}")
    if not gen_certs():
        print("S6: brak certow — pomijam.")
        return
    dc = ["docker", "compose", "-f", "docker-compose.yml",
          "-f", "docker-compose.tls.yml"]
    run_cmd(dc + ["up", "-d", "--build", "broker"], check=False)
    time.sleep(6)
    # Nazwa sieci compose (projekt = iot-edge-testbed)
    net = "iot-edge-testbed_default"
    ca = ["--cafile", "/certs/ca.crt"]
    results = []

    # Test 1 (uwierzytelnianie): klient anonimowy -> CONNACK odrzucony
    rc = _mqtt_try(net, ["mosquitto_sub", "-h", "broker", "-p", "8883"] + ca +
                   ["-t", "iot/+/telemetry", "-C", "1", "-W", "4"])
    results.append(("anonimowy dostep odrzucony (auth)", rc != 0))

    # Test 2 (autoryzacja/ACL): poprawny user 'device' probuje SUBSKRYBOWAC
    # alerty — ACL nie daje mu odczytu -> SUBACK failure -> brak wiadomosci
    rc = _mqtt_try(net, ["mosquitto_sub", "-h", "broker", "-p", "8883"] + ca +
                   ["-u", "device", "-P", "devicepass",
                    "-t", "alerts", "-C", "1", "-W", "4"])
    results.append(("ACL: 'device' nie czyta 'alerts'", rc != 0))

    # Kontrola POZYTYWNA: 'edge-node' MOZE publikowac na 'alerts' (ACL allow).
    # rc==0 dowodzi, ze broker dziala i akceptuje autoryzowanego klienta —
    # czyli wczesniejsze odrzucenia nie wynikaja z niedostepnosci brokera.
    rc = _mqtt_try(net, ["mosquitto_pub", "-h", "broker", "-p", "8883"] + ca +
                   ["-u", "edge-node", "-P", "edgepass",
                    "-t", "alerts", "-m", "test"])
    results.append(("autoryzowany 'edge-node' publikuje na 'alerts'", rc == 0))

    print("\n--- WYNIK S6 (PASS = zachowanie zgodne z polityka) ---")
    for name, ok in results:
        tag = ("PASS" if ok is True else "FAIL" if ok is False else ok)
        print(f"  [{tag}] {name}")
    print("Zapisz PASS/FAIL do tabeli S6 w pracy (PB4).")
    run_cmd(dc + ["down", "--timeout", "5"], check=False)


# ---------------------------------------------------------------------------
# extended — orkiestracja brakujacych serii (PB1 + PB5 + S7 + S6)
# ---------------------------------------------------------------------------
def run_extended(runs_pb1=30, runs_scale=10, duration=120, latency="60ms"):
    print("\n########## ROZSZERZONE SERIE: central + PB5 + S7 + S6 ##########")
    # Re-run CALEGO wariantu scentralizowanego (S1-S5) z toxiproxy + poprawiona
    # metryka S1. Wariant brzegowy pozostaje (jest wazny: edge nie uzywa
    # emulacji opoznienia, a kod edge/detektora sie nie zmienil).
    for sc in SCENARIOS:
        run_batch("central", sc, runs_pb1, duration, latency, 1)
    # PB5 — skalowalnosc (wariant brzegowy, mixed)
    run_scalability(runs_scale, duration, (1, 5, 10, 20), latency)
    # S7 — awaria wezla
    run_failure(180, 60, 30)
    # PB4/S6 — kontrola dostepu
    run_access_control()
    # Finalna, WSPOLNA agregacja edge (istniejace, wazne) + central (swieze)
    run_cmd([PY, "analyze/aggregate.py", "--data-root", DATA_ROOT,
             "--scenarios", "normal", "mixed", "flood", "payload", "value",
             "--locations", "edge", "central"], check=False)
    print("\n########## ROZSZERZONE SERIE ZAKONCZONE ##########")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scenario")
    p.add_argument("location", choices=["edge", "central"])
    p.add_argument("scenario", choices=SCENARIOS)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--latency", default="60ms")
    p.add_argument("--devices", type=int, default=1)

    p = sub.add_parser("batch")
    p.add_argument("location", choices=["edge", "central"])
    p.add_argument("scenario", choices=SCENARIOS)
    p.add_argument("runs", type=int)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--latency", default="60ms")
    p.add_argument("--devices", type=int, default=1)

    p = sub.add_parser("all")
    p.add_argument("--runs", type=int, default=30)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--latency", default="60ms")

    p = sub.add_parser("scalability")
    p.add_argument("--runs", type=int, default=10)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--counts", type=int, nargs="+", default=[1, 5, 10, 20])
    p.add_argument("--latency", default="60ms")

    p = sub.add_parser("failure")
    p.add_argument("--duration", type=int, default=180)
    p.add_argument("--kill-at", type=int, default=60)
    p.add_argument("--down", type=int, default=30)

    sub.add_parser("access-control")

    p = sub.add_parser("extended")
    p.add_argument("--runs-pb1", type=int, default=30)
    p.add_argument("--runs-scale", type=int, default=10)
    p.add_argument("--duration", type=int, default=120)
    p.add_argument("--latency", default="60ms")

    args = parser.parse_args()
    if args.command == "scenario":
        run_scenario(args.location, args.scenario, args.duration,
                     args.latency, args.devices)
    elif args.command == "batch":
        run_batch(args.location, args.scenario, args.runs, args.duration,
                  args.latency, args.devices)
    elif args.command == "all":
        run_all(args.runs, args.duration, args.latency)
    elif args.command == "scalability":
        run_scalability(args.runs, args.duration, tuple(args.counts),
                        args.latency)
    elif args.command == "failure":
        run_failure(args.duration, args.kill_at, args.down)
    elif args.command == "access-control":
        run_access_control()
    elif args.command == "extended":
        run_extended(args.runs_pb1, args.runs_scale, args.duration,
                     args.latency)


if __name__ == "__main__":
    main()
