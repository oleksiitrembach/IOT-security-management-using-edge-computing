"""Agregator wielu przebiegow -> srednia +/- CI95 na (wariant, scenariusz).
Poprawia dwa bledy wczesniejszego agregatu:
  * S1 (brak anomalii): precyzja/czulosc/F1 = nieokreslone (None), nie 0;
  * CI95 = 1.96 * sd / sqrt(n).
Uzycie:
  python analyze/aggregate_runs.py --data-root ./data/runs [--filter central_]
Katalogi przebiegow: <wariant>_<scenariusz>_<i>  (np. central_flood_3).
"""
import os, glob, math, statistics, argparse
import pandas as pd

def per_run(run_dir):
    gt_files = glob.glob(os.path.join(run_dir, "ground_truth_*.csv"))
    if not gt_files:
        return None
    gt = pd.concat([pd.read_csv(p) for p in gt_files], ignore_index=True)
    det_path = os.path.join(run_dir, "detections.csv")
    det = pd.read_csv(det_path).drop_duplicates("event_id") if os.path.exists(det_path) \
        else pd.DataFrame(columns=["event_id", "ts_alert"])
    m = gt.merge(det[["event_id", "ts_alert"]], on="event_id", how="left")
    m["detected"] = m["ts_alert"].notna()
    m["is_anomaly"] = m["is_anomaly"].astype(bool)
    TP = int((m.detected & m.is_anomaly).sum()); FP = int((m.detected & ~m.is_anomaly).sum())
    FN = int((~m.detected & m.is_anomaly).sum()); TN = int((~m.detected & ~m.is_anomaly).sum())
    has_anom = (TP + FN) > 0
    prec = TP / (TP + FP) if (TP + FP) else float("nan")
    rec = TP / (TP + FN) if (TP + FN) else float("nan")
    f1 = 2 * prec * rec / (prec + rec) if (has_anom and (TP + FP) and (prec + rec) > 0) else float("nan")
    fpr = FP / (FP + TN) if (FP + TN) else float("nan")
    if not has_anom:                       # S1: miary jakosci nieokreslone
        prec = rec = f1 = float("nan")
    tp = m[m.detected & m.is_anomaly].copy()
    tp["dt"] = (tp["ts_alert"] - tp["ts_pub"]) * 1000.0
    dt = tp["dt"]
    r = {"precision": prec, "recall": rec, "f1": f1, "fpr": fpr,
         "dt_mean": dt.mean() if len(dt) else float("nan"),
         "dt_median": dt.median() if len(dt) else float("nan"),
         "dt_p95": dt.quantile(0.95) if len(dt) else float("nan")}
    sp = os.path.join(run_dir, "edge_stats.csv")
    if os.path.exists(sp):
        s = pd.read_csv(sp)
        if len(s):
            r["cpu_mean"] = s.cpu_perc.mean(); r["cpu_p95"] = s.cpu_perc.quantile(0.95); r["ram_max"] = s.mem_mb.max()
    return r

def agg(vals):
    vals = [float(v) for v in vals if v == v]      # usun NaN
    if not vals:
        return float("nan"), float("nan")
    mean = statistics.fmean(vals)
    if len(vals) < 2:
        return mean, 0.0
    return mean, 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))

def fmt(mean, ci):
    return "—" if mean != mean else f"{mean:.3f}±{ci:.3f}"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="./data/runs")
    ap.add_argument("--filter", default="")
    args = ap.parse_args()
    groups = {}
    for d in sorted(glob.glob(os.path.join(args.data_root, "*"))):
        name = os.path.basename(d)
        if args.filter and not name.startswith(args.filter):
            continue
        if not os.path.isdir(d):
            continue
        key = name.rsplit("_", 1)[0]        # <wariant>_<scenariusz>
        r = per_run(d)
        if r:
            groups.setdefault(key, []).append(r)
    metrics = ["precision", "recall", "f1", "fpr", "dt_mean", "dt_median", "dt_p95",
               "cpu_mean", "cpu_p95", "ram_max"]
    print(f"{'grupa':<22}{'n':>4}  " + "  ".join(f"{m:>14}" for m in metrics))
    for key, runs in sorted(groups.items()):
        cells = []
        for m in metrics:
            mean, ci = agg([r.get(m, float("nan")) for r in runs])
            cells.append(fmt(mean, ci))
        print(f"{key:<22}{len(runs):>4}  " + "  ".join(f"{c:>14}" for c in cells))
