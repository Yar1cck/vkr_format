"""Лёгкая инструментация шагов pipeline для замера времени.

В проде overhead нулевой: если VKR_TIMING не выставлен — context manager пустой.
Включается через `enable_timing()` (тесты/бенчмарки) или env-переменной VKR_TIMING=1.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

_TIMING_ENABLED = os.environ.get("VKR_TIMING") == "1"


@dataclass
class TimingRecord:
    step: str
    duration_ms: float
    sequence: int


@dataclass
class TimingCollector:
    records: list[TimingRecord] = field(default_factory=list)
    _seq: int = 0

    def reset(self) -> None:
        self.records.clear()
        self._seq = 0

    def add(self, step: str, duration_ms: float) -> None:
        self._seq += 1
        self.records.append(TimingRecord(step=step, duration_ms=duration_ms, sequence=self._seq))

    def by_step(self) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for r in self.records:
            out.setdefault(r.step, []).append(r.duration_ms)
        return out


_collector = TimingCollector()


def enable_timing() -> None:
    global _TIMING_ENABLED
    _TIMING_ENABLED = True


def disable_timing() -> None:
    global _TIMING_ENABLED
    _TIMING_ENABLED = False


def is_enabled() -> bool:
    return _TIMING_ENABLED


def collector() -> TimingCollector:
    return _collector


def reset() -> None:
    _collector.reset()


@contextmanager
def timed(step: str):
    if not _TIMING_ENABLED:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        _collector.add(step, elapsed_ms)
