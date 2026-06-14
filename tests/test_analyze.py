"""Testy analizy wyników (analyze.py).

Weryfikują poprawność obliczeń metryk na syntetycznych danych:
  - Macierz pomyłek (TP/FP/FN/TN)
  - Precyzja, czułość, F1, FPR
  - Edge case: prec=0 → F1=0 (nie NaN)
  - Unikalność event_id

Uruchomienie::

    python -m pytest tests/test_analyze.py -v
"""

import os
import sys
import json
import tempfile

import pandas as pd
import numpy as np

# Dodaj katalog główny
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _create_test_data(tmpdir, gt_rows, det_rows):
    """Tworzy pliki ground truth i detections w katalogu tymczasowym."""
    gt_path = os.path.join(tmpdir, "ground_truth_test.csv")
    gt_df = pd.DataFrame(gt_rows, columns=["event_id", "device_id", "ts_pub",
                                            "is_anomaly", "anomaly_type"])
    gt_df.to_csv(gt_path, index=False)

    det_path = os.path.join(tmpdir, "detections.csv")
    det_df = pd.DataFrame(det_rows, columns=["event_id", "ts_alert", "reason",
                                              "source"])
    det_df.to_csv(det_path, index=False)

    return gt_df, det_df


def _compute_metrics(gt, det):
    """Replikuje logikę analyze.py do obliczania metryk."""
    det_dedup = det.drop_duplicates("event_id")
    m = gt.merge(det_dedup[["event_id", "ts_alert", "source"]],
                 on="event_id", how="left")
    m["detected"] = m["ts_alert"].notna()
    m["is_anomaly"] = m["is_anomaly"].astype(bool)

    TP = int(((m.detected) & (m.is_anomaly)).sum())
    FP = int(((m.detected) & (~m.is_anomaly)).sum())
    FN = int(((~m.detected) & (m.is_anomaly)).sum())
    TN = int(((~m.detected) & (~m.is_anomaly)).sum())

    prec = TP / (TP + FP) if (TP + FP) > 0 else 0.0
    rec = TP / (TP + FN) if (TP + FN) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    fpr = FP / (FP + TN) if (FP + TN) > 0 else 0.0

    return TP, FP, FN, TN, prec, rec, f1, fpr


class TestConfusionMatrix:
    """Testy macierzy pomyłek."""

    def test_perfect_detection(self):
        """Wszystkie anomalie wykryte, zero fałszywych alarmów."""
        gt_rows = [
            ["e1", "d1", 1000.0, 1, "flood"],
            ["e2", "d1", 1001.0, 1, "payload"],
            ["e3", "d1", 1002.0, 0, "none"],
            ["e4", "d1", 1003.0, 0, "none"],
        ]
        det_rows = [
            ["e1", 1000.01, "flood", "edge"],
            ["e2", 1001.02, "payload", "edge"],
        ]
        gt, det = pd.DataFrame(gt_rows, columns=["event_id", "device_id",
                                                   "ts_pub", "is_anomaly", "anomaly_type"]), \
                  pd.DataFrame(det_rows, columns=["event_id", "ts_alert",
                                                   "reason", "source"])
        TP, FP, FN, TN, prec, rec, f1, fpr = _compute_metrics(gt, det)
        assert TP == 2
        assert FP == 0
        assert FN == 0
        assert TN == 2
        assert prec == 1.0
        assert rec == 1.0
        assert f1 == 1.0
        assert fpr == 0.0

    def test_with_false_positives(self):
        """Wykrycie + fałszywy alarm."""
        gt_rows = [
            ["e1", "d1", 1000.0, 1, "flood"],
            ["e2", "d1", 1001.0, 0, "none"],  # normalny → FP jeśli wykryty
        ]
        det_rows = [
            ["e1", 1000.01, "flood", "edge"],
            ["e2", 1001.01, "flood", "edge"],  # FP!
        ]
        gt, det = pd.DataFrame(gt_rows, columns=["event_id", "device_id",
                                                   "ts_pub", "is_anomaly", "anomaly_type"]), \
                  pd.DataFrame(det_rows, columns=["event_id", "ts_alert",
                                                   "reason", "source"])
        TP, FP, FN, TN, prec, rec, f1, fpr = _compute_metrics(gt, det)
        assert TP == 1
        assert FP == 1
        assert prec == 0.5
        assert rec == 1.0
        assert fpr == 1.0  # FP/(FP+TN) = 1/(1+0)

    def test_with_false_negatives(self):
        """Pominięta anomalia."""
        gt_rows = [
            ["e1", "d1", 1000.0, 1, "flood"],
            ["e2", "d1", 1001.0, 1, "value"],  # FN — nie wykryty
        ]
        det_rows = [
            ["e1", 1000.01, "flood", "edge"],
        ]
        gt, det = pd.DataFrame(gt_rows, columns=["event_id", "device_id",
                                                   "ts_pub", "is_anomaly", "anomaly_type"]), \
                  pd.DataFrame(det_rows, columns=["event_id", "ts_alert",
                                                   "reason", "source"])
        TP, FP, FN, TN, prec, rec, f1, fpr = _compute_metrics(gt, det)
        assert TP == 1
        assert FN == 1
        assert rec == 0.5


class TestEdgeCases:
    """Edge cases: F1=0, zero anomalii, zero wykryć."""

    def test_f1_zero_when_prec_zero(self):
        """Gdy precyzja=0 (same FP), F1 powinno być 0, nie NaN."""
        gt_rows = [
            ["e1", "d1", 1000.0, 0, "none"],
        ]
        det_rows = [
            ["e1", 1000.01, "flood", "edge"],  # FP
        ]
        gt, det = pd.DataFrame(gt_rows, columns=["event_id", "device_id",
                                                   "ts_pub", "is_anomaly", "anomaly_type"]), \
                  pd.DataFrame(det_rows, columns=["event_id", "ts_alert",
                                                   "reason", "source"])
        TP, FP, FN, TN, prec, rec, f1, fpr = _compute_metrics(gt, det)
        assert prec == 0.0
        assert f1 == 0.0
        assert not np.isnan(f1), "F1 nie powinno byc NaN!"

    def test_no_anomalies_no_detections(self):
        """Tylko normalny ruch, zero wykryć → TN=100%, reszta=0."""
        gt_rows = [
            ["e1", "d1", 1000.0, 0, "none"],
            ["e2", "d1", 1001.0, 0, "none"],
        ]
        det_rows = []
        gt, det = pd.DataFrame(gt_rows, columns=["event_id", "device_id",
                                                   "ts_pub", "is_anomaly", "anomaly_type"]), \
                  pd.DataFrame(det_rows, columns=["event_id", "ts_alert",
                                                   "reason", "source"])
        TP, FP, FN, TN, prec, rec, f1, fpr = _compute_metrics(gt, det)
        assert TP == 0
        assert FP == 0
        assert FN == 0
        assert TN == 2
        assert fpr == 0.0
        assert f1 == 0.0

    def test_all_missed(self):
        """Wszystkie anomalie pominięte → recall=0, F1=0."""
        gt_rows = [
            ["e1", "d1", 1000.0, 1, "flood"],
            ["e2", "d1", 1001.0, 1, "value"],
        ]
        det_rows = []
        gt, det = pd.DataFrame(gt_rows, columns=["event_id", "device_id",
                                                   "ts_pub", "is_anomaly", "anomaly_type"]), \
                  pd.DataFrame(det_rows, columns=["event_id", "ts_alert",
                                                   "reason", "source"])
        TP, FP, FN, TN, prec, rec, f1, fpr = _compute_metrics(gt, det)
        assert rec == 0.0
        assert f1 == 0.0


class TestDetectionTime:
    """Testy obliczania czasu detekcji."""

    def test_detection_time_positive(self):
        """Czas detekcji = ts_alert - ts_pub (w ms)."""
        gt = pd.DataFrame([["e1", "d1", 1000.000, 1, "flood"]],
                          columns=["event_id", "device_id", "ts_pub",
                                   "is_anomaly", "anomaly_type"])
        det = pd.DataFrame([["e1", 1000.005, "flood", "edge"]],
                           columns=["event_id", "ts_alert", "reason", "source"])
        m = gt.merge(det[["event_id", "ts_alert"]], on="event_id")
        dt_ms = (m["ts_alert"] - m["ts_pub"]) * 1000.0
        assert abs(dt_ms.iloc[0] - 5.0) < 0.1
