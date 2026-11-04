"""Metriky prechodovej charakteristiky polohoveho servopohonu z CSV nastroja tools/test_position_step.py.

Len standardna kniznica (bezi na doske aj na PC). Profil sa rozdeli na useky: kazdy usek zacina prvou
vzorkou, v ktorej sa ziadana poloha zmeni (skok alebo zaciatok rampy), a konci pred dalsou takou zmenou.
"""
import csv
import math


def load_csv(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path}: prazdny subor")
    return {k: [float(r[k]) for r in rows] for k in rows[0]}


def segments(t, ref, min_hold_s=0.05):
    """Indexy (zaciatok, koniec) usekov. Zaciatok = prva zmena ziadanej polohy po aspon min_hold_s pokoja."""
    starts = []
    still_since = t[0]
    for i in range(1, len(ref)):
        if ref[i] != ref[i - 1]:
            if t[i - 1] - still_since >= min_hold_s:
                starts.append(i)
            still_since = t[i]
    return [(s, (starts[k + 1] if k + 1 < len(starts) else len(t))) for k, s in enumerate(starts)]


def step_metrics(t, ref, theta, s, e, band_pct=5.0, band_min_deg=1.0, ess_window_s=0.2):
    """Metriky jedneho useku [s, e). Pasmo ustalenia = max(band_pct % zo skoku, band_min_deg).

    band_min_deg je spodna hranica pasma: pri malych skokoch by 5 % bolo pod rozlisenim enkodera.
    """
    start = theta[s - 1] if s > 0 else theta[s]
    target = ref[e - 1]
    amp = target - start
    t0 = t[s]
    sign = 1.0 if amp >= 0 else -1.0
    out = {"t0_s": t0, "start_deg": start, "target_deg": target, "amp_deg": amp,
           "duration_s": t[e - 1] - t0}
    if abs(amp) < 1e-9:
        return out
    # doba nabehu 10 % -> 90 % (od zaciatku useku, aby zahrnula aj dopravne oneskorenie)
    t10 = t90 = None
    for i in range(s, e):
        p = (theta[i] - start) / amp
        if t10 is None and p >= 0.1:
            t10 = t[i] - t0
        if p >= 0.9:
            t90 = t[i] - t0
            break
    out["t10_s"], out["t90_s"] = t10, t90
    out["rise_s"] = (t90 - t10) if t10 is not None and t90 is not None else None
    peak = max(sign * (theta[i] - target) for i in range(s, e))
    out["overshoot_deg"] = max(0.0, peak)
    out["overshoot_pct"] = max(0.0, peak) / abs(amp) * 100.0
    band = max(abs(amp) * band_pct / 100.0, band_min_deg)
    out["band_deg"] = band
    settle = None
    for i in range(e - 1, s - 1, -1):
        if abs(theta[i] - target) > band:
            settle = (t[i + 1] - t0) if i + 1 < e else None    # None = neustalil sa do konca useku
            break
    else:
        settle = 0.0
    out["settle_s"] = settle
    tail = [theta[i] - target for i in range(s, e) if t[i] >= t[e - 1] - ess_window_s]
    out["ess_deg"] = sum(tail) / len(tail)
    err = [ref[i] - theta[i] for i in range(s, e)]
    out["err_rms_deg"] = math.sqrt(sum(x * x for x in err) / len(err))
    return out


def analyze(data, band_pct=5.0, band_min_deg=1.0):
    t, ref, th = data["t_s"], data["ref_deg"], data["theta_deg"]
    return [step_metrics(t, ref, th, s, e, band_pct, band_min_deg) for s, e in segments(t, ref)]
