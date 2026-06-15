"""S7 - analiza okna niedostepnosci wezla brzegowego."""
import os, glob, argparse
import pandas as pd

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="./data")
    args = ap.parse_args()
    D = args.data_dir
    fw = pd.read_csv(os.path.join(D, "failure_window.csv"))
    t_kill, t_up = float(fw.t_kill[0]), float(fw.t_up[0])
    gt = pd.concat([pd.read_csv(p) for p in glob.glob(os.path.join(D, "ground_truth_*.csv"))], ignore_index=True)
    det = pd.read_csv(os.path.join(D, "detections.csv")).drop_duplicates("event_id") \
        if os.path.exists(os.path.join(D, "detections.csv")) else pd.DataFrame(columns=["event_id", "ts_alert"])
    m = gt.merge(det[["event_id", "ts_alert"]], on="event_id", how="left")
    m["is_anomaly"] = m["is_anomaly"].astype(bool)
    win = m[(m.ts_pub >= t_kill) & (m.ts_pub <= t_up) & (m.is_anomaly)]
    detected_in_win = win["ts_alert"].notna().sum()
    total_win = len(win)
    # czas przywrocenia: pierwsza detekcja po t_up
    after = det[det["ts_alert"].astype(float) > t_up]
    recovery = (after["ts_alert"].astype(float).min() - t_up) if len(after) else float("nan")
    print("=== S7 awaria wezla (Tabela 7) ===")
    print(f"okno niedostepnosci: {t_up - t_kill:.1f} s")
    print(f"anomalie w oknie: {total_win}, wykryte: {detected_in_win}, "
          f"utracone (pokrycie): {total_win - detected_in_win} "
          f"({100*(total_win-detected_in_win)/total_win:.1f}% jesli >0)" if total_win else
          f"anomalie w oknie: 0")
    print(f"czas przywrocenia detekcji po restarcie: {recovery:.2f} s")
