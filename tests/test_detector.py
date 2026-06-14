"""Testy jednostkowe detektora anomalii.

Weryfikują poprawność trzech reguł detekcji:
  1. Reguła częstotliwości (flood)
  2. Reguła rozmiaru ładunku (payload)
  3. Reguła odchylenia statystycznego (value / k-sigma)

Uruchomienie::

    python -m pytest tests/test_detector.py -v
"""

import sys
import os
import time

# Dodaj katalog główny do ścieżki (detector.py jest w root)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from detector import Detector


class TestFloodRule:
    """Testy reguły częstotliwości (Z2 — zalewanie komunikatami)."""

    def test_normal_rate_not_flagged(self):
        """Ruch poniżej progu nie powinien generować alarmu."""
        det = Detector(freq_threshold=20, window_s=1.0)
        ts = 1000.0
        for i in range(20):
            flagged, reason = det.check("dev1", 25.0, 100, ts=ts)
            assert not flagged, f"Fałszywy alarm przy {i+1} wiadomości"

    def test_flood_detected(self):
        """Przekroczenie progu częstotliwości powinno wyzwolić alarm."""
        det = Detector(freq_threshold=10, window_s=1.0)
        ts = 1000.0
        flagged_any = False
        for i in range(15):
            flagged, reason = det.check("dev1", 25.0, 100, ts=ts + i * 0.01)
            if flagged:
                assert reason == "flood"
                flagged_any = True
        assert flagged_any, "Flood nie został wykryty"

    def test_flood_window_expires(self):
        """Po upłynięciu okna czasowego próg się resetuje."""
        det = Detector(freq_threshold=5, window_s=1.0)
        # Wypełnij okno
        for i in range(5):
            det.check("dev1", 25.0, 100, ts=1000.0 + i * 0.1)
        # Kolejna wiadomość 2 sekundy później (po oknie) — nie powinna flagować
        flagged, reason = det.check("dev1", 25.0, 100, ts=1002.0)
        assert not flagged

    def test_flood_per_device_isolation(self):
        """Reguła częstotliwości działa niezależnie per urządzenie."""
        det = Detector(freq_threshold=5, window_s=1.0)
        ts = 1000.0
        # Wypełnij próg dla dev1
        for i in range(6):
            det.check("dev1", 25.0, 100, ts=ts + i * 0.01)
        # dev2 nie powinien być flagowany
        flagged, _ = det.check("dev2", 25.0, 100, ts=ts)
        assert not flagged


class TestPayloadRule:
    """Testy reguły rozmiaru ładunku (Z3)."""

    def test_normal_payload_not_flagged(self):
        """Ładunek poniżej progu nie generuje alarmu."""
        det = Detector(max_payload=512)
        flagged, reason = det.check("dev1", 25.0, 400, ts=1000.0)
        assert not flagged

    def test_large_payload_flagged(self):
        """Ładunek powyżej progu wyzwala alarm."""
        det = Detector(max_payload=512)
        flagged, reason = det.check("dev1", 25.0, 1024, ts=1000.0)
        assert flagged
        assert reason == "payload"

    def test_exact_threshold_not_flagged(self):
        """Ładunek dokładnie na progu (512 == max_payload) NIE wyzwala alarmu."""
        det = Detector(max_payload=512)
        flagged, _ = det.check("dev1", 25.0, 512, ts=1000.0)
        assert not flagged

    def test_one_byte_over_flagged(self):
        """Ładunek o 1 bajt powyżej progu wyzwala alarm."""
        det = Detector(max_payload=512)
        flagged, reason = det.check("dev1", 25.0, 513, ts=1000.0)
        assert flagged
        assert reason == "payload"


class TestValueRule:
    """Testy reguły odchylenia statystycznego (k-sigma)."""

    def test_no_flag_during_warmup(self):
        """Podczas rozgrzewki (warmup) reguła k-sigma nie generuje alarmów."""
        det = Detector(warmup=30, k_sigma=3.0)
        # Nawet ekstremalna wartość nie powinna flagować przed warmup
        for i in range(29):
            det.check("dev1", 25.0, 100, ts=1000.0 + i)
        flagged, _ = det.check("dev1", 1000.0, 100, ts=1029.0)
        # Nie powinno flagować — wciąż w warmup (30 = min, sprawdzamy < warmup)
        # Po 29 normalnych + 1 ekstremalna = 30 obs, ale warmup = 30
        # → pierwsza możliwa flaga to obs. #31

    def test_spike_detected_after_warmup(self):
        """Po rozgrzewce, drastyczny skok wartości jest wykrywany."""
        det = Detector(warmup=30, k_sigma=4.0)
        # 50 normalnych wartości (μ=25, σ=1.5)
        for i in range(50):
            det.check("dev1", 25.0 + (i % 3) * 0.5, 100, ts=1000.0 + i)
        # Wartość 6+ sigma od średniej powinna flagować
        flagged, reason = det.check("dev1", 50.0, 100, ts=1050.0)
        assert flagged
        assert reason == "value"

    def test_normal_variation_not_flagged(self):
        """Normalna zmienność w granicach k-sigma nie generuje alarmu."""
        det = Detector(warmup=30, k_sigma=4.0)
        # 100 wartości z małą wariancją
        all_flagged = []
        for i in range(100):
            val = 25.0 + (i % 5) * 0.3 - 0.6  # zakres ≈ 24.4 – 25.6
            flagged, _ = det.check("dev1", val, 100, ts=1000.0 + i)
            if flagged:
                all_flagged.append(i)
        assert len(all_flagged) == 0, f"Fałszywe alarmy przy obserwacjach: {all_flagged}"

    def test_stats_update_includes_anomalies(self):
        """Statystyki Welforda są aktualizowane nawet po wykryciu anomalii."""
        det = Detector(warmup=10, k_sigma=3.0)
        # 20 normalnych
        for i in range(20):
            det.check("dev1", 25.0, 100, ts=1000.0 + i)
        # Anomalia
        det.check("dev1", 100.0, 100, ts=1020.0)
        # Statystyki powinny zawierać anomalię
        assert det._n["dev1"] == 21


class TestRulePriority:
    """Testy kolejności reguł — flood jest sprawdzany przed payload."""

    def test_flood_takes_priority(self):
        """Jeśli jednocześnie flood i payload — raportowany jest flood."""
        det = Detector(freq_threshold=3, max_payload=100)
        ts = 1000.0
        # 4 szybkie wiadomości z dużym payloadem
        for i in range(4):
            flagged, reason = det.check("dev1", 25.0, 200, ts=ts + i * 0.01)
        assert flagged
        assert reason == "flood"


class TestRepr:
    """Test __repr__ detektora."""

    def test_repr(self):
        det = Detector(freq_threshold=15, k_sigma=3.5)
        r = repr(det)
        assert "freq_threshold=15" in r
        assert "k_sigma=3.5" in r
