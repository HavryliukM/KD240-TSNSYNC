"""Rozvinutie uhla z enkodera (0..360) na viacotackovy uhol."""


class Unwrapper:
    """Pri kazdej vzorke pripocita najmensiu zmenu uhla (|delta| <= 180 stupnov).

    Funguje aj ked enkoder uz posiela viacotackovu hodnotu (vtedy skoky nie su).
    Podmienka: motor sa medzi dvoma vzorkami neotoci o viac ako 180 stupnov,
    teda rpm < 30 * vzorkovacia_frekvencia_hz (pri 200 Hz je to 6000 rpm).
    """

    def __init__(self):
        self._prev = None
        self.value = 0.0

    def reset(self):
        self._prev = None
        self.value = 0.0

    def update(self, raw_deg: float) -> float:
        if self._prev is None:
            self._prev = raw_deg
            self.value = raw_deg
            return self.value
        d = raw_deg - self._prev
        if d > 180.0 or d < -180.0:
            d -= 360.0 * round(d / 360.0)
        self.value += d
        self._prev = raw_deg
        return self.value
