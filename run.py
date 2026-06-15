"""Cross-platform experiment runner for IoT Edge Security Testbed.
Replaces bash scripts to ensure Windows/Linux/macOS compatibility.

Usage:
  python run.py scenario <location> <scenario> [duration] [device_count]
  python run.py batch <location> <scenario> <runs> [duration] [device_count]
  python run.py all [runs] [duration]
"""

import os
import sys
import time
import shutil
import subprocess
import argparse

DATA_ROOT = os.path.abspath(os.environ.get("DATA_DIR", "./data"))

def run_cmd(cmd, env=None, check=True):
    print(f"    > {' '.join(cmd)}")
    subprocess.run(cmd, env=env, check=check)

def init_toxiproxy(latency="60ms"):
    lat_val = latency.replace("ms", "")
    run_cmd(["docker", "exec", "iot-toxiproxy", "/toxiproxy-cli", "delete", "broker_proxy"], check=False)
    run_cmd(["docker", "exec", "iot-toxiproxy", "/toxiproxy-cli", "create", "broker_proxy", "--listen", "0.0.0.0:1883", "--upstream", "broker:1883"])
    run_cmd(["docker", "exec", "iot-toxiproxy", "/toxiproxy-cli", "toxic", "add", "broker_proxy", "--type", "latency", "--attribute", f"latency={lat_val}"])

def run_scenario(location, scenario, duration=120, latency="60ms", device_count=1, data_dir=DATA_ROOT):
    print(f"\n{'='*40}")
    print(f"  EXPERIMENT RUN")
    print(f"  Location: {location}")
    print(f"  Scenario: {scenario}")
    print(f"  Duration: {duration}s")
    print(f"  Devices:  {device_count}")
    if location == "central":
        print(f"  Latency:  {latency}")
    print(f"  Data dir: {data_dir}")
    print(f"{'='*40}\n")

    os.makedirs(data_dir, exist_ok=True)
    for f in ["detections.csv", "edge_stats.csv", "central_stats.csv", "edge_telemetry.csv", "central_telemetry.csv", "results.json"]:
        p = os.path.join(data_dir, f)
        if os.path.exists(p): os.remove(p)
    for p in os.listdir(data_dir):
        if p.startswith("ground_truth_") and p.endswith(".csv"):
            os.remove(os.path.join(data_dir, p))

    env = os.environ.copy()
    env["DETECTION_LOCATION"] = location
    env["SCENARIO"] = scenario
    env["DURATION"] = str(duration)
    env["LATENCY"] = latency
    env["DATA_DIR"] = data_dir

    try:
        # Cleanup first
        dc_cmd = ["docker", "compose", "-f", "docker-compose.yml"]
        if location == "central":
            dc_cmd.extend(["-f", "docker-compose.latency.yml"])

        run_cmd(dc_cmd + ["down", "--timeout", "5"], env=env, check=False)
            
        print(">> Starting broker, edge, central...")
        if location == "central":
            run_cmd(dc_cmd + ["up", "-d", "--build", "broker", "toxiproxy", "edge", "central"], env=env)
        else:
            run_cmd(dc_cmd + ["up", "-d", "--build", "broker", "edge", "central"], env=env)
        
        print(">> Waiting for broker health...")
        for i in range(30):
            res = subprocess.run(dc_cmd + ["exec", "broker", "mosquitto_pub", "-t", "healthcheck", "-m", "ok", "-q", "0"], env=env, capture_output=True)
            if res.returncode == 0:
                print(f"   Broker ready ({i}s)")
                break
            time.sleep(1)
        
        if location == "central":
            print(f">> Applying network delay via toxiproxy: {latency}")
            init_toxiproxy(latency=latency)
            
        print(f">> Starting {device_count} IoT device(s)...")
        run_cmd(dc_cmd + ["up", "--build", "--scale", f"device={device_count}", "device"], env=env)
        
        time.sleep(2)
        print(">> Stopping edge and central...")
        run_cmd(dc_cmd + ["stop", "--timeout", "10", "edge", "central"], env=env)
        
        print(">> Analyzing results...")
        run_cmd([sys.executable, "analyze/analyze.py"], env=env)
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        run_cmd(dc_cmd + ["down", "--timeout", "5"], env=env, check=False)

def run_batch(location, scenario, runs, duration=120, latency="60ms", device_count=1):
    print(f"\n{'='*60}")
    print(f"  BATCH RUN: {location} x {scenario}")
    print(f"  Runs: {runs}, Duration: {duration}s, Devices: {device_count}")
    print(f"{'='*60}\n")
    
    failed = 0
    for i in range(1, runs + 1):
        run_dir = os.path.join(DATA_ROOT, f"{location}_{scenario}_run{i:02d}")
        print(f"\n>> Run #{i}/{runs} [Dir: {run_dir}]")
        if os.path.exists(run_dir):
            shutil.rmtree(run_dir)
        os.makedirs(run_dir, exist_ok=True)
        
        success = run_scenario(location, scenario, duration, latency, device_count, data_dir=run_dir)
        if not success:
            failed += 1
            print(f"   WARNING: Run #{i} failed.")
            
        time.sleep(3)
        
    print(f"\n>> Batch finished. {runs-failed}/{runs} successful.")
    print(">> Aggregating results...")
    run_cmd([sys.executable, "analyze/aggregate.py", "--data-root", DATA_ROOT, "--scenarios", scenario, "--locations", location])

def run_all(runs=30, duration=120, latency="60ms"):
    scenarios = ["normal", "mixed", "flood", "payload", "value"]
    locations = ["edge", "central"]
    
    for scenario in scenarios:
        for location in locations:
            run_batch(location, scenario, runs, duration, latency, device_count=1)
            
    # Scalability S6
    for location in locations:
        run_batch(location, "mixed", runs, duration, latency, device_count=5)
        
    print("\n>> Final global aggregation...")
    run_cmd([sys.executable, "analyze/aggregate.py", "--data-root", DATA_ROOT])
    print("\nALL DONE! Check data/aggregate_results.json and charts.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Scenario
    p_scen = subparsers.add_parser("scenario")
    p_scen.add_argument("location", choices=["edge", "central"])
    p_scen.add_argument("scenario", choices=["normal", "mixed", "flood", "payload", "value"])
    p_scen.add_argument("--duration", type=int, default=120)
    p_scen.add_argument("--latency", default="60ms")
    p_scen.add_argument("--devices", type=int, default=1)
    
    # Batch
    p_batch = subparsers.add_parser("batch")
    p_batch.add_argument("location", choices=["edge", "central"])
    p_batch.add_argument("scenario", choices=["normal", "mixed", "flood", "payload", "value"])
    p_batch.add_argument("runs", type=int)
    p_batch.add_argument("--duration", type=int, default=120)
    p_batch.add_argument("--latency", default="60ms")
    p_batch.add_argument("--devices", type=int, default=1)
    
    # All
    p_all = subparsers.add_parser("all")
    p_all.add_argument("--runs", type=int, default=30)
    p_all.add_argument("--duration", type=int, default=120)
    p_all.add_argument("--latency", default="60ms")
    
    args = parser.parse_args()
    
    if args.command == "scenario":
        run_scenario(args.location, args.scenario, args.duration, args.latency, args.devices)
    elif args.command == "batch":
        run_batch(args.location, args.scenario, args.runs, args.duration, args.latency, args.devices)
    elif args.command == "all":
        run_all(args.runs, args.duration, args.latency)
