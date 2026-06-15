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
- **Central variant:** Detection runs on the central system, reached through a
  directional latency proxy (`toxiproxy`, downstream broker→central) that
  simulates the path to a cloud region. This replaces egress-only `tc netem`,
  which could not inject latency on the inbound telemetry path.
- **Difference = impact of processing location** on detection time (PB1/H1).

## Requirements

- Docker + Docker Compose v2 (`docker compose version`)
- Python 3.12+ on the host (canonical runner `run.py` + analysis scripts)
- Bash is **optional** — the `scripts/*.sh` are thin wrappers that delegate to
  `run.py`, so on Windows you can run everything with `python run.py ...`.

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
python run.py scenario edge mixed --duration 120
# central variant (clean ~60 ms cloud latency via toxiproxy):
python run.py scenario central mixed --duration 120 --latency 60ms
```

`run.py` performs the full, correct lifecycle for every run
(down → clean data dir → up → wait broker → [central: toxiproxy latency] →
run device(s) → stop edge+central to flush CSVs → down) and then runs the
per-run analysis automatically.

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
# Base cycle: 5 scenarios × 2 variants × 30 repetitions
python run.py all --runs 30 --duration 120

# Extended series (PB1 clean central, PB5 scalability, S7 failure, PB4/S6):
python run.py extended --runs-pb1 30 --runs-scale 10 --duration 120

# Quick smoke test (one short central run)
python run.py scenario central flood --duration 20
```

## Individual Research Series

```bash
# PB1 — clean central detection time (toxiproxy), 30 runs per scenario
python run.py batch central flood 30 --latency 60ms

# PB5 — scalability sweep (edge, mixed) over device counts
python run.py scalability --runs 10 --counts 1 5 10 20

# S7 — edge node failure and recovery
python run.py failure --duration 180 --kill-at 60 --down 30

# PB4/S6 — access control (TLS + ACL); generates certs in a container
python run.py access-control
```

Devices scale via `--devices N`; each replica gets a unique `DEVICE_ID` from
its container hostname (PB5).

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
python run.py batch edge mixed 30

# 30 runs of central × mixed (with 60ms toxiproxy latency)
python run.py batch central mixed 30 --latency 60ms

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
- Cloud latency emulated via a `toxiproxy` directional latency proxy on the
  broker→central path (limitation: emulation, not real WAN — noted in §7.5).
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
