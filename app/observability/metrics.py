"""Простые счётчики метрик без внешних зависимостей.

На этапе 1 — минимальные счётчики в памяти. Полная интеграция с
prometheus-client выполняется на этапе 8 (Observability).
"""

import threading
import time


class Metrics:
    """Счётчики Latency, RPS, TPS и типов ПД."""

    #: Сколько последних значений latency хранить для расчёта p95/p99.
    _LATENCY_WINDOW = 1000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests_total = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._latencies: list[float] = []
        self._tokens_total = 0
        self._masked_types_total: dict[str, int] = {}
        self._started = time.time()

    def observe(self, latency_seconds: float, tokens: int) -> None:
        with self._lock:
            self._requests_total += 1
            self._latency_sum += latency_seconds
            self._latency_count += 1
            self._latencies.append(latency_seconds)
            if len(self._latencies) > self._LATENCY_WINDOW:
                self._latencies = self._latencies[-self._LATENCY_WINDOW :]
            self._tokens_total += tokens

    def inc_masked_type(self, type_: str) -> None:
        """Инкрементирует счётчик замаскированных типов ПД."""
        with self._lock:
            self._masked_types_total[type_] = self._masked_types_total.get(type_, 0) + 1

    def _percentile(self, pct: float) -> float:
        """Квантиль по последним latency."""
        if not self._latencies:
            return 0.0
        sorted_lat = sorted(self._latencies)
        idx = min(int(len(sorted_lat) * pct), len(sorted_lat) - 1)
        return sorted_lat[idx]

    def snapshot(self) -> dict:
        with self._lock:
            uptime = time.time() - self._started
            rps = self._requests_total / uptime if uptime > 0 else 0.0
            avg_latency = self._latency_sum / self._latency_count if self._latency_count else 0.0
            return {
                "requests_total": self._requests_total,
                "rps": round(rps, 3),
                "avg_latency_seconds": round(avg_latency, 6),
                "latency_p50_seconds": round(self._percentile(0.50), 6),
                "latency_p95_seconds": round(self._percentile(0.95), 6),
                "latency_p99_seconds": round(self._percentile(0.99), 6),
                "tokens_total": self._tokens_total,
                "masked_types_total": dict(self._masked_types_total),
                "uptime_seconds": round(uptime, 3),
            }


metrics = Metrics()