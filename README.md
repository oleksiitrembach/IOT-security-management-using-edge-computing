# IoT Edge Security Testbed

Reproducible containerized environment for a master's thesis on IoT security
management using edge computing. Compares anomaly detection at the **edge node**
vs. the **central system** using Docker containers with cgroup resource limits
and `tc netem` network emulation.

> **Thesis:** *Zarządzanie bezpieczeństwem sieci IoT z wykorzystaniem
> przetwarzania brzegowego (edge computing)*

## Architecture

```
┌──────────────┐     MQTT      ┌──────────────┐
│  Device(s)   │─────────────▶│    Broker     │
│  (simulator) │              │  (Mosquitto)  │
└──────────────┘              └──────┬───┬────┘
                                     │   │
                              ┌──────┘   └──────┐
                              ▼                  ▼
                     ┌──────────────┐   ┌──────────────┐
                     │  Edge Node   │   │   Central    │
                     │  (1 CPU,     │   │   System     │
                     │   512MB)     │   │  (+ netem)   │
                     │  detection   │   │  detection   │
                     │  (edge mode) │   │  (central)   │
                     └──────────────┘   └──────────────┘
```

- **Edge variant:** Detection runs on the edge node (local, no latency).
- **Central variant:** Detection runs on the central system, loaded with
  network latency (`tc netem`) simulating the path to a cloud region.
- **Difference = impact of processing location** on detection time (PB1/H1).

## Requirements

- Docker + Docker Compose v2 (`docker compose version`)
- Python 3.12+ on the host (for analysis scripts)
- Bash (Git Bash on Windows, or WSL)

## Quick Start

```bash
# 1. Clone and enter
git clone https://github.com/oleksiitrembach/IOT-security-management-using-edge-computing.git
cd IOT-security-management-using-edge-computing

# 2. Set up Python environment (host — for analysis)
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
pip install -r analyze/requirements-analyze.txt

# 3. Run a single experiment (edge variant, mixed scenario, 2 min)
DETECTION_LOCATION=edge SCENARIO=mixed DURATION=120 ./scripts/run_scenario.sh

# 4. Analyze results
DATA_DIR=./data VARIANT=edge python analyze/analyze.py
```

## Scenario Mapping (Thesis Table 3)

| `SCENARIO` | Thesis | Measures |
|------------|--------|----------|
| `normal`   | S1 — Normal traffic only | FPR, resource baseline |
| `mixed`    | S2 — Increased load (5% anomalies) | Scalability, resources |
| `flood`    | S3 — Message flooding | Detection time, recall |
| `payload`  | S4 — Payload size anomaly   | Precision of size rule    |
| `value`    | S5 — Value spike (k-sigma) | Statistical rule recall |
| (N/A)      | S6 — Access Control        | TLS/ACL verification      |
| (N/A)      | S7 — Edge node failure     | System resilience         |

## Research Question Mapping

| PB | Question | How measured |
|----|----------|-------------|
| PB1 | Edge vs central detection time | `ts_alert − ts_pub` per variant |
| PB2 | Detection effectiveness | Precision, recall, F1, FPR |
| PB3 | Edge node resource usage | CPU%, RAM via `psutil` |
| PB4 | Access control impact (S5) | TLS/ACL overlay comparison |
| PB5 | Scalability | `--scale device=N` |

## Running All Experiments

```bash
# Full cycle: 5 scenarios × 2 variants × 30 repetitions ≈ 12h
./scripts/run_all_experiments.sh

# Quick smoke test: 3 runs × 30s
RUNS=3 DURATION=30 ./scripts/run_all_experiments.sh
```

## Manual Step-by-Step

```bash
# 1. Start infrastructure
DETECTION_LOCATION=edge docker compose up -d --build broker edge central

# 2. (central only) Add latency emulation
./scripts/apply_netem.sh add 60ms

# 3. Run devices (blocks until DURATION expires)
SCENARIO=flood DURATION=120 docker compose up --build device

# 4. Stop with graceful shutdown
docker compose stop --timeout 10 edge central

# 5. Analyze
DATA_DIR=./data VARIANT=edge python analyze/analyze.py

# 6. Cleanup
docker compose down
```

## Scaling Devices (PB5)

```bash
SCENARIO=mixed DEVICE_COUNT=10 ./scripts/run_scenario.sh
```

Each replica gets a unique `DEVICE_ID` from its container hostname.

## Scenario S5 — TLS + ACL

```bash
# Generate certificates
./scripts/gen_certs.sh

# Run with TLS overlay
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d
```

## Output Files

| File | Thesis Table |
|------|-------------|
| `data/detections.csv` | Tables 4 & 5 |
| `data/ground_truth_*.csv` | Tables 4 & 5 |
| `data/edge_stats.csv` | Table 6 |
| `data/central_stats.csv` | Table 6 |
| `data/edge_telemetry.csv` | Table 7 |
| `data/central_telemetry.csv` | Table 7 |
| `data/results.json` | Aggregation input |
| `data/aggregate_results.json` | Final aggregated tables |
| `data/fig_*.png` | Figure 4 |

## Batch Runs & Aggregation

```bash
# 30 runs of edge × mixed
./scripts/run_batch.sh edge mixed 30

# 30 runs of central × mixed (with 60ms latency)
./scripts/run_batch.sh central mixed 30 60ms

# Aggregate results across all runs
python analyze/aggregate.py --data-root ./data
```

## Parameters (Environment Variables)

See [.env.example](.env.example) for all parameters with descriptions.

## Detection Rules (Thesis §4.5)

1. **Frequency rule** — Sliding window counts messages per device per second.
   Exceeding `FREQ_THRESHOLD` → flood alert (Z2).
2. **Payload size rule** — Messages larger than `MAX_PAYLOAD` bytes → payload
   alert (Z3).
3. **Statistical deviation (k-sigma)** — After `WARMUP` observations, values
   outside μ ± k·σ → value alert. Uses Welford's online algorithm.

## Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Methodology Notes (Thesis §6)

- **n ≥ 30 repetitions** per scenario/variant for statistical significance.
- All containers share the host clock → no NTP synchronization needed.
- Cloud latency emulated via `tc netem` on the central container
  (limitation: emulation, not real WAN — noted in §7.5).
- Resource measurement via `psutil` inside containers (process-level,
  more precise than `docker stats`).
- Edge node limited to 1 CPU / 512 MB via cgroups — emulates constrained
  IoT gateway.

## Reproducibility

```bash
# Anyone can reproduce:
git clone <repo>
docker compose up
# Same results on any Docker-capable machine.
```

## License

MIT — see [LICENSE](LICENSE).
