"""Agregacja wynikow do tabel rozdzialu 7. Uruchom na hoscie:
    pip install -r analyze/requirements-analyze.txt
    DATA_DIR=./data VARIANT=brzegowy python analyze/analyze.py
"""
import os, glob
import pandas as pd

DATA_DIR = os.getenv("DATA_DIR", "./data")
VARIANT = os.getenv("VARIANT", "wariant")

gt_files = glob.glob(os.path.join(DATA_DIR, "ground_truth_*.csv"))
if not gt_files:
    raise SystemExit("Brak plikow ground_truth_*.csv w " + DATA_DIR)
gt = pd.concat([pd.read_csv(p) for p in gt_files], ignore_index=True)
det = pd.read_csv(os.path.join(DATA_DIR, "detections.csv")).drop_duplicates("event_id")

m = gt.merge(det[["event_id", "ts_alert", "source"]], on="event_id", how="left")
m["detected"] = m["ts_alert"].notna()
m["is_anomaly"] = m["is_anomaly"].astype(bool)

TP = int(((m.detected) & (m.is_anomaly)).sum())
FP = int(((m.detected) & (~m.is_anomaly)).sum())
FN = int(((~m.detected) & (m.is_anomaly)).sum())
TN = int(((~m.detected) & (~m.is_anomaly)).sum())
prec = TP / (TP + FP) if (TP + FP) else float("nan")
rec = TP / (TP + FN) if (TP + FN) else float("nan")
f1 = 2 * prec * rec / (prec + rec) if (prec and rec) else float("nan")
fpr = FP / (FP + TN) if (FP + TN) else float("nan")

print(f"\n=== Wariant: {VARIANT} ===")
print("--- Skutecznosc detekcji (Tabela 5) ---")
print(f"TP={TP} FP={FP} FN={FN} TN={TN}")
print(f"precyzja={prec:.3f}  czulosc={rec:.3f}  F1={f1:.3f}  FPR={fpr:.3f}")

tp = m[(m.detected) & (m.is_anomaly)].copy()
tp["dt_ms"] = (tp["ts_alert"] - tp["ts_pub"]) * 1000.0
dt = tp["dt_ms"]
print("--- Czas detekcji [ms] (Tabela 4) ---")
if len(dt):
    print(f"srednia={dt.mean():.1f}  mediana={dt.median():.1f}  "
          f"p95={dt.quantile(0.95):.1f}  std={dt.std():.1f}  n={len(dt)}")
else:
    print("brak wykrytych incydentow (TP=0)")

stats_path = os.path.join(DATA_DIR, "edge_stats.csv")
if os.path.exists(stats_path):
    s = pd.read_csv(stats_path)
    print("--- Zasoby wezla brzegowego (Tabela 6) ---")
    print(f"CPU sr={s.cpu_perc.mean():.1f}%  CPU p95={s.cpu_perc.quantile(0.95):.1f}%  "
          f"RAM sr={s.mem_mb.mean():.1f} MB  RAM max={s.mem_mb.max():.1f} MB")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if len(dt):
        plt.figure()
        plt.boxplot(dt, vert=True, tick_labels=[VARIANT])
        plt.ylabel("Czas detekcji [ms]")
        plt.title("Rozklad czasu detekcji")
        out = os.path.join(DATA_DIR, f"detection_time_{VARIANT}.png")
        plt.savefig(out, dpi=150, bbox_inches="tight")
        print("Zapisano wykres:", out)
except Exception as e:
    print("pominieto wykres:", e)
