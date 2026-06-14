"""Lekki detektor anomalii dla węzła brzegowego / systemu centralnego.
Łączy trzy reguły zgodne z rozdz. 4.5 pracy:
  1) reguła częstotliwości (przeciw zalewowi komunikatów, Z2),
  2) reguła rozmiaru ładunku (anomalia treści/rozmiaru, Z3),
  3) statystyczne wykrywanie odchyleń wartości (k-sigma, po okresie rozgrzewki).
Kod własny — biblioteki zewnętrzne nie są tu używane.
"""
import time
from collections import deque, defaultdict


class Detector:
    def __init__(self, freq_threshold=20, window_s=1.0, max_payload=512,
                 warmup=30, k_sigma=4.0):
        self.freq_threshold = freq_threshold
        self.window_s = window_s
        self.max_payload = max_payload
        self.warmup = warmup
        self.k_sigma = k_sigma
        self._times = defaultdict(deque)     # device -> deque[ts]
        self._n = defaultdict(int)
        self._mean = defaultdict(float)
        self._m2 = defaultdict(float)        # Welford

    def _update_stats(self, device, value):
        self._n[device] += 1
        n = self._n[device]
        delta = value - self._mean[device]
        self._mean[device] += delta / n
        self._m2[device] += delta * (value - self._mean[device])

    def _std(self, device):
        n = self._n[device]
        return (self._m2[device] / (n - 1)) ** 0.5 if n >= 2 else 0.0

    def check(self, device, value, payload_len, ts=None):
        """Zwraca (flagged: bool, reason: str)."""
        ts = time.time() if ts is None else ts
        # 1) częstotliwość w oknie przesuwnym
        dq = self._times[device]
        dq.append(ts)
        while dq and ts - dq[0] > self.window_s:
            dq.popleft()
        if len(dq) > self.freq_threshold:
            return True, "flood"
        # 2) rozmiar ładunku
        if payload_len > self.max_payload:
            return True, "payload"
        # 3) odchylenie statystyczne (po rozgrzewce)
        std = self._std(device)
        flagged, reason = False, "none"
        if self._n[device] >= self.warmup and std > 0 \
                and abs(value - self._mean[device]) > self.k_sigma * std:
            flagged, reason = True, "value"
        self._update_stats(device, value)
        return flagged, reason
