"""Lekki detektor anomalii dla węzła brzegowego / systemu centralnego.

Łączy trzy reguły zgodne z rozdz. 4.5 pracy:
  1) reguła częstotliwości — przeciw zalewowi komunikatów (zagrożenie Z2),
  2) reguła rozmiaru ładunku — anomalia treści/rozmiaru (zagrożenie Z3),
  3) statystyczne wykrywanie odchyleń wartości — k-sigma, po okresie
     rozgrzewki (warmup).

Projekt świadomie nie wykorzystuje uczenia maszynowego:
  - zasoby węzła brzegowego są ograniczone (1 CPU / 512 MB),
  - reguły progowe dają powtarzalność i interpretowalność,
  - ML wymagałby zbierania danych treningowych, co wykracza poza zakres PB.

Kod własny — biblioteki zewnętrzne nie są tu używane.
"""

import time
from collections import deque, defaultdict


class Detector:
    """Detektor anomalii oparty na trzech regułach progowych.

    Parameters
    ----------
    freq_threshold : int
        Maksymalna liczba wiadomości w oknie ``window_s`` zanim reguła
        częstotliwości sygnalizuje atak flood (zagrożenie Z2).
    window_s : float
        Długość okna przesuwnego [s] dla reguły częstotliwości.
    max_payload : int
        Maksymalny rozmiar ładunku [B]. Przekroczenie = anomalia payload.
    warmup : int
        Minimalna liczba obserwacji przed włączeniem reguły k-sigma.
        W fazie rozgrzewki zbierane są statystyki, ale nie zgłaszane alerty.
    k_sigma : float
        Mnożnik odchylenia standardowego. Wartość spoza przedziału
        [μ − k·σ, μ + k·σ] oznacza anomalię wartości.
    """

    def __init__(self, freq_threshold=20, window_s=1.0, max_payload=512,
                 warmup=30, k_sigma=4.0):
        self.freq_threshold = freq_threshold
        self.window_s = window_s
        self.max_payload = max_payload
        self.warmup = warmup
        self.k_sigma = k_sigma

        # Okno przesuwne timestampów per device (reguła częstotliwości)
        self._times = defaultdict(deque)
        # Algorytm Welforda — obliczanie średniej i wariancji online
        self._n = defaultdict(int)
        self._mean = defaultdict(float)
        self._m2 = defaultdict(float)

    def __repr__(self):
        return (f"Detector(freq_threshold={self.freq_threshold}, "
                f"window_s={self.window_s}, max_payload={self.max_payload}, "
                f"warmup={self.warmup}, k_sigma={self.k_sigma})")

    def _update_stats(self, device, value):
        """Aktualizuje statystyki Welforda po sprawdzeniu bieżącej wartości."""
        self._n[device] += 1
        n = self._n[device]
        delta = value - self._mean[device]
        self._mean[device] += delta / n
        self._m2[device] += delta * (value - self._mean[device])

    def _std(self, device):
        """Odchylenie standardowe (z poprawką Bessela)."""
        n = self._n[device]
        return (self._m2[device] / (n - 1)) ** 0.5 if n >= 2 else 0.0

    def check(self, device, value, payload_len, ts=None):
        """Sprawdza bieżącą wiadomość pod kątem anomalii.

        WAŻNE — kolejność operacji:
          1. Reguła częstotliwości (okno przesuwne)
          2. Reguła rozmiaru ładunku
          3. Reguła odchylenia wartości — sprawdzenie PRZED aktualizacją
             statystyk, żeby bieżąca wartość nie wpływała na decyzję o sobie.
          4. Aktualizacja statystyk Welforda (włącznie z anomaliami, żeby
             model adaptował się do zmieniającej się dystrybucji).

        Returns
        -------
        tuple[bool, str]
            (flagged, reason) — ``True`` jeśli wykryto anomalię,
            ``reason`` ∈ {"flood", "payload", "value", "none"}.
        """
        ts = time.time() if ts is None else ts

        # --- Reguła 1: częstotliwość w oknie przesuwnym (Z2) ---
        dq = self._times[device]
        dq.append(ts)
        while dq and ts - dq[0] > self.window_s:
            dq.popleft()
        if len(dq) > self.freq_threshold:
            # Aktualizujemy statystyki nawet przy flood, żeby warmup postępował
            self._update_stats(device, value)
            return True, "flood"

        # --- Reguła 2: rozmiar ładunku (Z3) ---
        if payload_len > self.max_payload:
            self._update_stats(device, value)
            return True, "payload"

        # --- Reguła 3: odchylenie statystyczne (k-sigma, po rozgrzewce) ---
        # Sprawdzamy PRZED update — bieżąca wartość nie wpływa na decyzję
        std = self._std(device)
        flagged, reason = False, "none"
        if (self._n[device] >= self.warmup
                and std > 0
                and abs(value - self._mean[device]) > self.k_sigma * std):
            flagged, reason = True, "value"

        # Aktualizacja statystyk ZAWSZE (nawet dla anomalii), żeby model
        # nie stagnował po serii normalnych wartości
        self._update_stats(device, value)
        return flagged, reason
