"""PB5 - agregacja przebiegow skalowalnosci scale_<N>_<i> w tabele wg N."""
import os, glob, math, statistics, argparse
import pandas as pd

def per_run(d, duration):
    gt_files = glob.glob(os.path.join(d, "ground_truth_*.csv"))
    if not gt_files:
        return None
    gt = pd.concat([pd.read_csv(p) for p in gt_files], ignore_index=True)
    det = pd.read_csv(os.path.join(d, "detections.csv")).drop_duplicates("event_id") \
        if os.path.exists(os.path.join(d, "detections.csv")) else pd.DataFrame(columns=["event_id", "ts_alert"])
    m = gt.merge(det[["event_id", "ts_alert"]], on="event_id", how="left")
    tp = m[m["ts_alert"].notna() & m["is_anomaly"].astype(bool)].copy()
    tp["dt"] = (tp["ts_alert"] - tp["ts_pub"]) * 1000.0
    r = {"dt_mean": tp["dt"].mean() if len(tp) else float("nan"),
         "throughput": len(m) / duration}
    sp = os.path.join(d, "edge_stats.csv")
    if os.path.exists(sp):
        s = pd.read_csv(sp)
        if len(s):
            r["cpu_mean"] = s.cpu_perc.mean(); r["ram_max"] = s.mem_mb.max()
    return r

def agg(vals):
    vals = [float(v) for v in vals if v == v]
    if not vals: return float("nan"), float("nan")
    if len(vals) < 2: return statistics.fmean(vals), 0.0
    return statistics.fmean(vals), 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="./data/runs")
    ap.add_argument("--duration", type=float, default=120)
    args = ap.parse_args()
    byN = {}
    for d in sorted(glob.glob(os.path.join(args.data_root, "scale_*"))):
        if not os.path.isdir(d): continue
        n = int(os.path.basename(d).split("_")[1])
        r = per_run(d, args.duration)
        if r: byN.setdefault(n, []).append(r)
    print(f"{'N urzadzen':>10}{'czas det. [ms]':>18}{'CPU [%]':>14}{'RAM [MB]':>12}{'przepust. [msg/s]':>20}")
    for n in sorted(byN):
        runs = byN[n]
        dt = agg([r.get("dt_mean", float('nan')) for r in runs])
        cpu = agg([r.get("cpu_mean", float('nan')) for r in runs])
        ram = agg([r.get("ram_max", float('nan')) for r in runs])
        th = agg([r.get("throughput", float('nan')) for r in runs])
        print(f"{n:>10}{dt[0]:>13.1f}±{dt[1]:.1f}{cpu[0]:>10.2f}±{cpu[1]:.2f}{ram[0]:>9.1f}{th[0]:>17.1f}")
