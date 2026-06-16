"""Agregacja wyników z wielu przebiegów (≥ 30 runów) do finalnych tabel.

Zbiera pliki ``results.json`` z katalogów
``data/{location}_{scenario}_runXX/`` i oblicza:
- średnią, medianę, SD, P95, CI 95% dla każdej metryki,
- porównawcze wykresy pudełkowe (edge vs central na jednym rysunku → Rys. 4).

Uruchomienie::

    python analyze/aggregate.py --data-root ./data --scenarios mixed flood payload value normal

Wyniki: ``data/aggregate_results.json`` + ``data/fig_*.png``.
"""

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
import numpy as np
import pandas as pd

# Wymuś UTF-8 dla print() w konsoli Windows
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def load_runs(data_root, location, scenario):
    """Wczytuje results.json ze wszystkich runów dla danego location×scenario."""
    pattern = os.path.join(data_root, f"{location}_{scenario}_run*", "results.json")
    files = sorted(glob.glob(pattern))
    results = []
    for f in files:
        with open(f) as fp:
            results.append(json.load(fp))
    return results


def ci95(values):
    """95% confidence interval (t-distribution approx for n≥30)."""
    n = len(values)
    if n < 2:
        return 0.0
    std = np.std(values, ddof=1)
    # z = 1.96 for large n; for n=30 t≈2.045, acceptable approximation
    z = 1.96 if n >= 30 else 2.045
    return z * std / np.sqrt(n)


def aggregate_metric(runs, extractor):
    """Wyciąga jedną metrykę z listy runów i oblicza statystyki."""
    values = []
    for r in runs:
        v = extractor(r)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            values.append(v)
    if not values:
        return None
    arr = np.array(values, dtype=float)
    return {
        "mean": round(float(np.mean(arr)), 4),
        "median": round(float(np.median(arr)), 4),
        "std": round(float(np.std(arr, ddof=1)), 4) if len(arr) >= 2 else 0.0,
        "p5": round(float(np.percentile(arr, 5)), 4),
        "p95": round(float(np.percentile(arr, 95)), 4),
        "min": round(float(np.min(arr)), 4),
        "max": round(float(np.max(arr)), 4),
        "ci95": round(float(ci95(arr)), 4),
        "n": len(arr),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Agregacja wyników z wielu przebiegów eksperymentalnych")
    parser.add_argument("--data-root", default="./data",
                        help="Katalog główny z wynikami runów")
    parser.add_argument("--scenarios", nargs="+",
                        default=["normal", "mixed", "flood", "payload", "value"],
                        help="Scenariusze do agregacji")
    parser.add_argument("--locations", nargs="+", default=["edge", "central"],
                        help="Warianty lokalizacji detekcji")
    parser.add_argument("--min-runs", type=int, default=3,
                        help="Minimalna liczba runów do agregacji (ostrzeżenie)")
    args = parser.parse_args()

    all_results = {}
    all_dt_data = defaultdict(dict)  # scenario -> location -> list[float]

    for scenario in args.scenarios:
        for location in args.locations:
            runs = load_runs(args.data_root, location, scenario)
            if not runs:
                print(f"  [{location}/{scenario}] brak danych — pomijam")
                continue
            if len(runs) < args.min_runs:
                print(f"  UWAGA: [{location}/{scenario}] tylko {len(runs)} "
                      f"runow (min. {args.min_runs})")

            variant = "brzegowy" if location == "edge" else "scentralizowany"
            key = f"{location}_{scenario}"

            # Zbieramy metryki
            agg = {
                "location": location,
                "variant": variant,
                "scenario": scenario,
                "n_runs": len(runs),
                "precision": aggregate_metric(runs, lambda r: r.get("precision")),
                "recall": aggregate_metric(runs, lambda r: r.get("recall")),
                "f1": aggregate_metric(runs, lambda r: r.get("f1")),
                "fpr": aggregate_metric(runs, lambda r: r.get("fpr")),
                "detection_time_mean": aggregate_metric(
                    runs, lambda r: r.get("detection_time", {}).get("mean")),
                "detection_time_median": aggregate_metric(
                    runs, lambda r: r.get("detection_time", {}).get("median")),
                "detection_time_p95": aggregate_metric(
                    runs, lambda r: r.get("detection_time", {}).get("p95")),
            }

            # Zasoby
            for node in ["edge", "central"]:
                agg[f"cpu_mean_{node}"] = aggregate_metric(
                    runs, lambda r, n=node: r.get("resources", {}).get(n, {}).get("cpu_mean"))
                agg[f"cpu_p95_{node}"] = aggregate_metric(
                    runs, lambda r, n=node: r.get("resources", {}).get(n, {}).get("cpu_p95"))
                agg[f"mem_mean_{node}"] = aggregate_metric(
                    runs, lambda r, n=node: r.get("resources", {}).get(n, {}).get("mem_mean"))
                agg[f"mem_max_{node}"] = aggregate_metric(
                    runs, lambda r, n=node: r.get("resources", {}).get(n, {}).get("mem_max"))

            # Straty pakietów
            agg["packet_loss_rate"] = aggregate_metric(
                runs, lambda r: r.get("packets", {}).get("loss_rate"))

            all_results[key] = agg

            # Zbieramy surowe czasy detekcji do wykresu
            dt_values = [r.get("detection_time", {}).get("mean")
                         for r in runs
                         if r.get("detection_time", {}).get("mean") is not None]
            if dt_values:
                all_dt_data[scenario][location] = dt_values

            # Drukowanie
            print(f"\n{'='*60}")
            print(f"  {variant.upper()} / {scenario.upper()} "
                  f"({len(runs)} runow)")
            print(f"{'='*60}")
            for metric_name, metric_data in agg.items():
                if isinstance(metric_data, dict) and "mean" in metric_data:
                    print(f"  {metric_name:30s}: "
                          f"mean={metric_data['mean']:.4f}  "
                          f"std={metric_data['std']:.4f}  "
                          f"CI95=±{metric_data['ci95']:.4f}  "
                          f"n={metric_data['n']}")

    # ---------------------------------------------------------------------------
    # Zapis zbiorczy
    # ---------------------------------------------------------------------------
    out_path = os.path.join(args.data_root, "aggregate_results.json")
    with open(out_path, "w") as fp:
        json.dump(all_results, fp, indent=2, ensure_ascii=False)
    print(f"\nZapisano wyniki zbiorcze: {out_path}")

    # ---------------------------------------------------------------------------
    # Wykresy porównawcze (Rysunek 4 — edge vs central)
    # ---------------------------------------------------------------------------
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # Wykres 1: Czas detekcji — edge vs central per scenariusz
        for scenario, loc_data in all_dt_data.items():
            if len(loc_data) < 2:
                continue
            fig, ax = plt.subplots(figsize=(8, 5))
            labels = []
            data_sets = []
            colors = []
            for loc in ["edge", "central"]:
                if loc in loc_data:
                    labels.append("Brzegowy" if loc == "edge" else "Scentralizowany")
                    data_sets.append(loc_data[loc])
                    colors.append("#4C72B0" if loc == "edge" else "#DD8452")

            bp = ax.boxplot(data_sets, patch_artist=True, tick_labels=labels)
            for patch, color in zip(bp["boxes"], colors):
                patch.set_facecolor(color)
                patch.set_alpha(0.7)
            for median in bp["medians"]:
                median.set_color("white")
                median.set_linewidth(2)

            ax.set_ylabel("Średni czas detekcji [ms]")
            ax.set_title(f"Porównanie czasu detekcji — scenariusz {scenario}")
            ax.grid(axis="y", alpha=0.3)

            out = os.path.join(args.data_root, f"fig_compare_{scenario}.png")
            fig.savefig(out, dpi=150, bbox_inches="tight")
            plt.close(fig)
            print(f"Wykres: {out}")

        # Wykres 2: F1 per scenariusz (bar chart)
        scenarios_with_data = [s for s in args.scenarios
                               if any(f"{loc}_{s}" in all_results
                                      for loc in args.locations)]
        if scenarios_with_data:
            fig, ax = plt.subplots(figsize=(10, 5))
            x = np.arange(len(scenarios_with_data))
            width = 0.35
            for i, loc in enumerate(["edge", "central"]):
                f1_means = []
                f1_errs = []
                for s in scenarios_with_data:
                    key = f"{loc}_{s}"
                    if key in all_results and all_results[key]["f1"]:
                        f1_means.append(all_results[key]["f1"]["mean"])
                        f1_errs.append(all_results[key]["f1"]["ci95"])
                    else:
                        f1_means.append(0)
                        f1_errs.append(0)
                color = "#4C72B0" if loc == "edge" else "#DD8452"
                label = "Brzegowy" if loc == "edge" else "Scentralizowany"
                ax.bar(x + (i - 0.5) * width, f1_means, width, yerr=f1_errs,
                       label=label, color=color, alpha=0.8, capsize=4)

            ax.set_xlabel("Scenariusz")
            ax.set_ylabel("F1-score")
            ax.set_title("Porównanie F1-score — wariant brzegowy vs scentralizowany")
            ax.set_xticks(x)
            ax.set_xticklabels(scenarios_with_data)
            ax.legend()
            ax.set_ylim(0, 1.05)
            ax.grid(axis="y", alpha=0.3)

            out = os.path.join(args.data_root, "fig_f1_comparison.png")
            fig.savefig(out, dpi=150, bbox_inches="tight")
            plt.close(fig)
            print(f"Wykres: {out}")

        # Wykres 3: CPU/RAM porównanie
        cpu_edge = []
        cpu_central = []
        labels_cpu = []
        for s in scenarios_with_data:
            edge_key = f"edge_{s}"
            central_key = f"central_{s}"
            if (edge_key in all_results
                    and all_results[edge_key].get("cpu_mean_edge")
                    and central_key in all_results
                    and all_results[central_key].get("cpu_mean_central")):
                labels_cpu.append(s)
                cpu_edge.append(all_results[edge_key]["cpu_mean_edge"]["mean"])
                cpu_central.append(all_results[central_key]["cpu_mean_central"]["mean"])

        if labels_cpu:
            fig, ax = plt.subplots(figsize=(10, 5))
            x = np.arange(len(labels_cpu))
            width = 0.35
            ax.bar(x - width / 2, cpu_edge, width, label="Brzegowy",
                   color="#4C72B0", alpha=0.8)
            ax.bar(x + width / 2, cpu_central, width, label="Scentralizowany",
                   color="#DD8452", alpha=0.8)
            ax.set_xlabel("Scenariusz")
            ax.set_ylabel("Średnie CPU [%]")
            ax.set_title("Porównanie obciążenia CPU — Tabela 6")
            ax.set_xticks(x)
            ax.set_xticklabels(labels_cpu)
            ax.legend()
            ax.grid(axis="y", alpha=0.3)

            out = os.path.join(args.data_root, "fig_cpu_comparison.png")
            fig.savefig(out, dpi=150, bbox_inches="tight")
            plt.close(fig)
            print(f"Wykres: {out}")

    except ImportError:
        print("matplotlib/numpy niedostepne — pominieto wykresy")
    except Exception as e:
        print(f"Blad wykresow: {e}")

    # ---------------------------------------------------------------------------
    # Tabele w formacie Markdown (do wklejenia w pracę)
    # ---------------------------------------------------------------------------
    print(f"\n{'='*70}")
    print("  TABELE DO PRACY (format Markdown)")
    print(f"{'='*70}")

    # Tabela 4: Czas detekcji
    print("\n### Tabela 4. Czas detekcji anomalii [ms]")
    print("| Scenariusz | Wariant | Średnia | Mediana | P95 | SD | CI 95% | n |")
    print("|------------|---------|---------|---------|-----|----|--------|---|")
    for s in args.scenarios:
        for loc in args.locations:
            key = f"{loc}_{s}"
            if key not in all_results:
                continue
            r = all_results[key]
            dt_mean = r.get("detection_time_mean")
            dt_med = r.get("detection_time_median")
            dt_p95 = r.get("detection_time_p95")
            if dt_mean:
                print(f"| {s} | {r['variant']} | "
                      f"{dt_mean['mean']:.1f} | {dt_med['mean']:.1f} | "
                      f"{dt_p95['mean']:.1f} | {dt_mean['std']:.1f} | "
                      f"±{dt_mean['ci95']:.1f} | {dt_mean['n']} |")

    # Tabela 5: Skuteczność detekcji
    print("\n### Tabela 5. Skuteczność detekcji")
    print("| Scenariusz | Wariant | Precyzja | Czułość | F1 | FPR |")
    print("|------------|---------|----------|---------|----|----|")
    for s in args.scenarios:
        for loc in args.locations:
            key = f"{loc}_{s}"
            if key not in all_results:
                continue
            r = all_results[key]
            p = r.get("precision")
            rc = r.get("recall")
            f = r.get("f1")
            fp = r.get("fpr")
            if p and rc and f and fp:
                print(f"| {s} | {r['variant']} | "
                      f"{p['mean']:.3f}±{p['ci95']:.3f} | "
                      f"{rc['mean']:.3f}±{rc['ci95']:.3f} | "
                      f"{f['mean']:.3f}±{f['ci95']:.3f} | "
                      f"{fp['mean']:.4f}±{fp['ci95']:.4f} |")

    print("\nGotowe. Uzyj danych z aggregate_results.json do rozdzialu 7 pracy.")


if __name__ == "__main__":
    main()
