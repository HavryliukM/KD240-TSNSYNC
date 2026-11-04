"""Tabulka kompenzacie coggingu: dopredne napatie podla absolutneho uhla rotora (uhol z kniznice, 0..360).

Vznik tabulky (tools/build_cogging_table.py): pomala rampa cez celu otacku hore aj dole, pre kazdy stupen
priemer vystupu regulatora pri pohybe hore a dole. Suche trenie ma v smeroch opacne znamienko a vyrusi sa,
ostane zlozka zavisla len od uhla (cogging). Polovica rozdielu smerov je odhad trenia (pre kfc_v).

Plati len kym je uhol z kniznice viazany na rotor rovnako (overit po restarte dosky, PLAN: raw_deg v CSV).
"""
import csv


class CoggingTable:
    def __init__(self, values, gain=1.0):
        self.values = [float(v) for v in values]
        self.n = len(self.values)
        self.gain = float(gain)

    def __call__(self, angle_deg):
        """Linearna interpolacia medzi binmi, uhol sa berie modulo 360."""
        x = (float(angle_deg) % 360.0) * self.n / 360.0
        i = int(x) % self.n
        f = x - int(x)
        return self.gain * (self.values[i] * (1.0 - f) + self.values[(i + 1) % self.n] * f)

    def save(self, path):
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["angle_deg", "u"])
            for i, v in enumerate(self.values):
                w.writerow([f"{i * 360.0 / self.n:.3f}", f"{v:.5f}"])


def load(path, gain=1.0, limit=None):
    with open(path, newline="") as f:
        vals = [float(r["u"]) for r in csv.DictReader(f)]
    if not vals:
        raise ValueError(f"{path}: prazdna tabulka coggingu")
    if limit is not None:
        vals = [max(-limit, min(limit, v)) for v in vals]
    return CoggingTable(vals, gain)


def _smooth(vals, window):
    n, h = len(vals), window // 2
    return [sum(vals[(i + k) % n] for k in range(-h, h + 1)) / (2 * h + 1) for i in range(n)]


def _fill(vals):
    """Doplni prazdne biny (None) linearne medzi susednymi plnymi, kruhovo."""
    n = len(vals)
    known = [i for i, v in enumerate(vals) if v is not None]
    if not known:
        raise ValueError("ziadne data pre tabulku")
    out = list(vals)
    for k, i in enumerate(known):
        j = known[(k + 1) % len(known)]
        gap = (j - i) % n or n
        for s in range(1, gap):
            out[(i + s) % n] = vals[i] + (vals[j] - vals[i]) * s / gap
    return out


def build(data, bins=360, smooth=5):
    """Z dat rampy (stlpce t_s, ref_deg, u, raw_deg) vrati (CoggingTable, odhad trenia [V], pokrytie)."""
    ref, u, raw = data["ref_deg"], data["u"], data["raw_deg"]
    acc = {+1: [[0.0, 0] for _ in range(bins)], -1: [[0.0, 0] for _ in range(bins)]}
    for i in range(1, len(ref)):
        d = ref[i] - ref[i - 1]
        if d == 0.0:
            continue                                # zaujima nas len pohyb (rampa), nie drzanie
        b = int((raw[i] % 360.0) * bins / 360.0) % bins
        a = acc[1 if d > 0 else -1][b]
        a[0] += u[i]
        a[1] += 1
    mean = {s: [(a[0] / a[1]) if a[1] else None for a in acc[s]] for s in acc}
    both = sum(1 for b in range(bins) if mean[1][b] is not None and mean[-1][b] is not None)
    if both < bins // 2:
        raise ValueError(f"rampa pokryva oba smery len v {both} z {bins} binov, treba celu otacku hore aj dole")
    cog, fric = [], []
    for b in range(bins):
        up, dn = mean[1][b], mean[-1][b]
        if up is None or dn is None:
            cog.append(None)
            continue
        cog.append((up + dn) / 2.0)
        fric.append((up - dn) / 2.0)
    cog = _fill(cog)
    offset = sum(cog) / bins                    # stredna hodnota nie je cogging (napr. nesymetria), odcita sa
    cog = [v - offset for v in cog]
    if smooth > 1:
        cog = _smooth(cog, smooth)
    return CoggingTable(cog), sum(fric) / len(fric), both / bins
