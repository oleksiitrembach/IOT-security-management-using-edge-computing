"""Analiza wyników pojedynczego przebiegu — Tabele 4–7, Rysunek 4.

Uruchomienie::

    pip install -r analyze/requirements-analyze.txt
    DATA_DIR=./data VARIANT=brzegowy python analyze/analyze.py

Wyniki są wypisywane na stdout i zapisywane do ``results.json``
(do automatycznej agregacji przez ``aggregate.py``).
"""

import os
import sys
import glob
import json

import pandas as pd

DATA_DIR = os.getenv("DATA_DIR", "./data")
VARIANT = os.getenv("VARIANT") or os.getenv("DETECTION_LOCATION") or "brzegowy"
if VARIANT == "edge":
    VARIANT = "brzegowy"
elif VARIANT == "central":
    VARIANT = "scentralizowany"

# ---------------------------------------------------------------------------
# Wczytywanie danych
# ---------------------------------------------------------------------------
gt_files = glob.glob(os.path.join(DATA_DIR, "ground_truth_*.csv"))
if not gt_files:
    print("BLAD: Brak plikow ground_truth_*.csv w " + DATA_DIR, file=sys.stderr)
    sys.exit(1)

gt = pd.concat([pd.read_csv(p) for p in gt_files], ignore_index=True)

det_path = os.path.join(DATA_DIR, "detections.csv")
if not os.path.exists(det_path):
    print("BLAD: Brak pliku detections.csv w " + DATA_DIR, file=sys.stderr)
    sys.exit(1)

det = pd.read_csv(det_path).drop_duplicates("event_id")

# Walidacja: event_id musi być unikalne w ground truth
assert gt["event_id"].is_unique, \
    f"event_id nie jest unikalne w ground_truth! Duplikaty: {gt[gt.duplicated('event_id')]['event_id'].tolist()[:5]}"

# ---------------------------------------------------------------------------
# Macierz pomyłek (Tabela 5)
# ---------------------------------------------------------------------------
m = gt.merge(det[["event_id", "ts_alert", "source"]], on="event_id", how="left")
m["detected"] = m["ts_alert"].notna()
m["is_anomaly"] = m["is_anomaly"].astype(bool)

TP = int(((m.detected) & (m.is_anomaly)).sum())
FP = int(((m.detected) & (~m.is_anomaly)).sum())
FN = int(((~m.detected) & (m.is_anomaly)).sum())
TN = int(((~m.detected) & (~m.is_anomaly)).sum())

has_anom = (TP + FN) > 0
prec = TP / (TP + FP) if (TP + FP) > 0 else None
rec = TP / (TP + FN) if (TP + FN) > 0 else None
f1 = 2 * prec * rec / (prec + rec) if (has_anom and prec is not None and rec is not None and (prec + rec) > 0) else None
fpr = FP / (FP + TN) if (FP + TN) > 0 else 0.0

if not has_anom:
    prec = rec = f1 = None

print(f"\n{'='*50}")
print(f"  Wariant: {VARIANT}")
print(f"{'='*50}")

def _fmt(x):
    """'—' dla miar nieokreślonych (S1: brak anomalii → 0/0), inaczej 4 miejsca."""
    return "—" if x is None else f"{x:.4f}"

print("\n--- Skutecznosc detekcji (Tabela 5) ---")
print(f"  TP = {TP}   FP = {FP}   FN = {FN}   TN = {TN}")
print(f"  Precyzja  = {_fmt(prec)}")
print(f"  Czulosc   = {_fmt(rec)}")
print(f"  F1        = {_fmt(f1)}")
print(f"  FPR       = {fpr:.4f}")

# ---------------------------------------------------------------------------
# Czas detekcji (Tabela 4)
# ---------------------------------------------------------------------------
tp_rows = m[(m.detected) & (m.is_anomaly)].copy()
tp_rows["dt_ms"] = (tp_rows["ts_alert"] - tp_rows["ts_pub"]) * 1000.0
dt = tp_rows["dt_ms"]

print("\n--- Czas detekcji [ms] (Tabela 4) ---")
dt_stats = {}
if len(dt):
    dt_stats = {
        "mean": round(dt.mean(), 2),
        "median": round(dt.median(), 2),
        "p95": round(dt.quantile(0.95), 2),
        "std": round(dt.std(), 2),
        "min": round(dt.min(), 2),
        "max": round(dt.max(), 2),
        "n": int(len(dt)),
    }
    print(f"  Srednia  = {dt_stats['mean']:.1f} ms")
    print(f"  Mediana  = {dt_stats['median']:.1f} ms")
    print(f"  P95      = {dt_stats['p95']:.1f} ms")
    print(f"  Std      = {dt_stats['std']:.1f} ms")
    print(f"  Min      = {dt_stats['min']:.1f} ms")
    print(f"  Max      = {dt_stats['max']:.1f} ms")
    print(f"  n (TP)   = {dt_stats['n']}")
else:
    print("  Brak wykrytych incydentow (TP=0)")

# ---------------------------------------------------------------------------
# Zasoby węzła brzegowego (Tabela 6)
# ---------------------------------------------------------------------------
resource_stats = {}
for label, csv_name in [("edge", "edge_stats.csv"), ("central", "central_stats.csv")]:
    stats_path = os.path.join(DATA_DIR, csv_name)
    if os.path.exists(stats_path):
        s = pd.read_csv(stats_path)
        if len(s) > 0:
            rs = {
                "cpu_mean": round(s.cpu_perc.mean(), 2),
                "cpu_p95": round(s.cpu_perc.quantile(0.95), 2),
                "cpu_max": round(s.cpu_perc.max(), 2),
                "mem_mean": round(s.mem_mb.mean(), 2),
                "mem_max": round(s.mem_mb.max(), 2),
                "n_samples": int(len(s)),
            }
            resource_stats[label] = rs
            print(f"\n--- Zasoby [{label}] (Tabela 6) ---")
            print(f"  CPU srednia = {rs['cpu_mean']:.1f}%")
            print(f"  CPU P95     = {rs['cpu_p95']:.1f}%")
            print(f"  CPU max     = {rs['cpu_max']:.1f}%")
            print(f"  RAM srednia = {rs['mem_mean']:.1f} MB")
            print(f"  RAM max     = {rs['mem_max']:.1f} MB")
            print(f"  Probki      = {rs['n_samples']}")

# ---------------------------------------------------------------------------
# Straty pakietów (Tabela 7)
# ---------------------------------------------------------------------------
packet_stats = {}
telemetry_name = "edge_telemetry.csv" if VARIANT == "brzegowy" else "central_telemetry.csv"
telemetry_path = os.path.join(DATA_DIR, telemetry_name)
if os.path.exists(telemetry_path):
    t = pd.read_csv(telemetry_path)
    published = len(gt)
    received = len(t)
    lost = published - received
    rate = lost / published if published > 0 else 0.0
    packet_stats = {
        "published": int(published),
        "received": int(received),
        "lost": int(lost),
        "loss_rate": round(rate, 6),
    }
    print(f"\n--- Straty pakietow (Tabela 7) ---")
    print(f"  Wyslano   = {published}")
    print(f"  Odebrano  = {received}")
    print(f"  Stracono  = {lost}")
    print(f"  Wskaznik  = {rate:.4f}")
else:
    print(f"\n--- Brak pliku {telemetry_name} do obliczenia strat pakietow ---")

# ---------------------------------------------------------------------------
# Zapis do JSON (do agregacji przez aggregate.py)
# ---------------------------------------------------------------------------
results = {
    "variant": VARIANT,
    "confusion_matrix": {"TP": TP, "FP": FP, "FN": FN, "TN": TN},
    "precision": prec,
    "recall": rec,
    "f1": f1,
    "fpr": fpr,
    "detection_time": dt_stats,
    "resources": resource_stats,
    "packets": packet_stats,
}
results_path = os.path.join(DATA_DIR, "results.json")
with open(results_path, "w") as fp:
    json.dump(results, fp, indent=2, ensure_ascii=False)
print(f"\nZapisano wyniki do: {results_path}")

# ---------------------------------------------------------------------------
# Wykres pudełkowy (Rysunek 4)
# ---------------------------------------------------------------------------
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if len(dt):
        fig, ax = plt.subplots(figsize=(6, 4))
        bp = ax.boxplot(dt, vert=True, patch_artist=True,
                        boxprops=dict(facecolor="#4C72B0", alpha=0.7),
                        medianprops=dict(color="white", linewidth=2))
        ax.set_xticklabels([VARIANT])
        ax.set_ylabel("Czas detekcji [ms]")
        ax.set_title(f"Rozkład czasu detekcji — wariant {VARIANT}")
        ax.grid(axis="y", alpha=0.3)

        # Adnotacje statystyk
        stats_text = (f"μ = {dt.mean():.1f} ms\n"
                      f"Me = {dt.median():.1f} ms\n"
                      f"P95 = {dt.quantile(0.95):.1f} ms\n"
                      f"n = {len(dt)}")
        ax.text(0.95, 0.95, stats_text, transform=ax.transAxes,
                verticalalignment="top", horizontalalignment="right",
                fontsize=9, bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

        out = os.path.join(DATA_DIR, f"detection_time_{VARIANT}.png")
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"Zapisano wykres: {out}")
except ImportError:
    print("matplotlib niedostepne — pominieto wykres")
except Exception as e:
    print(f"Blad wykresu: {e}")
