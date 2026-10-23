"""Periodicka slucka s absolutnymi terminmi a statistikou jitteru."""
import os
import time


def try_realtime(priority: int = 50) -> bool:
    """Skusi SCHED_FIFO (vyzaduje root). Vrati True ak sa podarilo."""
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(priority))
        return True
    except (PermissionError, AttributeError, OSError):
        return False


class PeriodicLoop:
    def __init__(self, period_s: float, spin_s: float = 0.0):
        self._period = int(period_s * 1e9)
        self._spin = int(spin_s * 1e9)
        self._next = time.monotonic_ns()
        self.n = 0
        self.overruns = 0
        self._sum = 0
        self.max_jitter_ns = 0

    def wait(self) -> int:
        """Pocka na dalsi termin, vrati cas v ns (monotonic)."""
        self._next += self._period
        now = time.monotonic_ns()
        if now > self._next + self._period:
            self.overruns += 1
            self._next = now
        remaining = self._next - now
        if remaining > self._spin:
            time.sleep((remaining - self._spin) / 1e9)
        if self._spin:
            while time.monotonic_ns() < self._next:
                pass
        t = time.monotonic_ns()
        j = max(0, t - self._next)
        self.n += 1
        self._sum += j
        if j > self.max_jitter_ns:
            self.max_jitter_ns = j
        return t

    def stats(self) -> dict:
        return {"cycles": self.n, "overruns": self.overruns,
                "mean_jitter_us": (self._sum / self.n / 1e3) if self.n else 0.0,
                "max_jitter_us": self.max_jitter_ns / 1e3}
