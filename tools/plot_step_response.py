#!/usr/bin/env python3
"""Vyhodnotenie a graf prechodovej charakteristiky z CSV nastrojov tools/test_position_step.py (poloha)
a tools/test_speed_step.py (rychlost, rozpozna sa podla stlpca ref_rpm) na PC.

Vypise pre kazdy usek profilu: skok, dobu nabehu 10-90 %, prekmit, dobu ustalenia, trvalu odchylku
a RMS chyby. Graf (poloha, chyba, rychlost, vystup regulatora) ulozi ako PNG vedla CSV.
Metriky potrebuju len standardnu kniznicu, graf potrebuje matplotlib (pip install matplotlib).

Pouzitie:
  python tools/plot_step_response.py step20.csv
  python tools/plot_step_response.py step20.csv --band 2 --show
  python tools/plot_step_response.py a.csv b.csv --no-plot
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kd240sync.step_metrics import analyze, load_csv


def fmt(x, scale=1.0, unit="", nd=1):
    return "-" if x is None else f"{x * scale:.{nd}f}{unit}"


def print_metrics(path, res, band_pct):
    print(f"\n{path}")
    print(f"{'t0 [s]':>7} | {'skok':>13} | {'nabeh':>8} | {'prekmit':>15} | {'ustalenie':>10} | "
          f"{'e_ss':>6} | {'RMS':>5}")
    print("-" * 80)
    for m in res:
        if abs(m["amp_deg"]) < 1e-9:
            continue
        print(f"{m['t0_s']:7.3f} | {m['start_deg']:5.1f}->{m['target_deg']:5.1f} | "
              f"{fmt(m['rise_s'], 1e3, ' ms', 0):>8} | "
              f"{m['overshoot_pct']:5.1f} % {m['overshoot_deg']:4.1f} deg | "
              f"{fmt(m['settle_s'], 1e3, ' ms', 0):>10} | {m['ess_deg']:+6.2f} | {m['err_rms_deg']:5.2f}")
    print(f"nabeh = 10 -> 90 %, ustalenie do pasma max({band_pct:g} % skoku, 1 deg), "
          f"'-' = neustalil sa do konca useku; e_ss a RMS v deg, e_ss = priemer poslednych 0.2 s")


SPEED_SMOOTH_S = 0.005        # kĺzavý priemer rýchlosti pre časové metriky (odhad v knižnici šumí +-15..30 rpm)
SPEED_BAND_MIN = 10.0         # spodná hranica pásma ustálenia rýchlosti [ot/min]


def smooth(t, v, window_s):
    """Centrovaný kĺzavý priemer s oknom window_s."""
    dt = (t[-1] - t[0]) / max(1, len(t) - 1)
    h = max(0, int(round(window_s / dt / 2)))
    out, acc = [], 0.0
    pre = [0.0]
    for x in v:
        acc += x
        pre.append(acc)
    for i in range(len(v)):
        a, b = max(0, i - h), min(len(v), i + h + 1)
        out.append((pre[b] - pre[a]) / (b - a))
    return out


def analyze_speed(data, band_pct):
    data = dict(data)
    data["speed_f"] = smooth(data["t_s"], data["speed_rpm"], SPEED_SMOOTH_S)
    res = analyze(data, band_pct, SPEED_BAND_MIN, "ref_rpm", "speed_f", ess_window_s=0.5)
    raw = analyze(data, band_pct, SPEED_BAND_MIN, "ref_rpm", "speed_rpm", ess_window_s=0.5)
    for m, r in zip(res, raw):
        m["ripple_raw"] = r.get("ripple_std")
    return data, res


def print_speed_metrics(path, res, band_pct):
    print(f"\n{path}  (rychlost, casove metriky z klzaveho priemeru {SPEED_SMOOTH_S * 1e3:.0f} ms)")
    print(f"{'t0 [s]':>7} | {'skok [ot/min]':>13} | {'nabeh':>8} | {'prekmit':>16} | {'ustalenie':>10} | "
          f"{'e_ss':>7} | {'zvlnenie':>8}")
    print("-" * 88)
    for m in res:
        if abs(m["amp_deg"]) < 1e-9:
            continue
        print(f"{m['t0_s']:7.3f} | {m['start_deg']:5.0f}->{m['target_deg']:5.0f} | "
              f"{fmt(m['rise_s'], 1e3, ' ms', 0):>8} | "
              f"{m['overshoot_pct']:5.1f} % {m['overshoot_deg']:5.1f} rpm | "
              f"{fmt(m['settle_s'], 1e3, ' ms', 0):>10} | {m['ess_deg']:+7.1f} | {m['ripple_raw']:8.1f}")
    print(f"ustalenie do pasma max({band_pct:g} % skoku, {SPEED_BAND_MIN:g} ot/min); e_ss = priemer odchylky "
          f"poslednych 0,5 s [ot/min]; zvlnenie = smerodajna odchylka surovej rychlosti v tom okne [ot/min]")


def plot_speed(path, data, res, show):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = data["t_s"]
    has_u = "u" in data and any(x == x for x in data["u"])
    has_i = any(k in data and any(x == x for x in data[k]) for k in ("i_q", "i_d"))
    rows = 1 + has_u + has_i
    fig, ax = plt.subplots(rows, 1, sharex=True, figsize=(10, 3.2 + 2.2 * rows),
                           gridspec_kw={"height_ratios": [2] + [1] * (rows - 1)}, squeeze=False)
    ax = list(ax[:, 0])
    ax[0].plot(t, data["speed_rpm"], color="0.75", lw=0.6, label="skutočná (surová)")
    ax[0].plot(t, data["speed_f"], lw=1.1, label=f"skutočná (priemer {SPEED_SMOOTH_S * 1e3:.0f} ms)")
    ax[0].plot(t, data["ref_rpm"], "k--", lw=1, label="žiadaná")
    ax[0].set_ylabel("rýchlosť [ot/min]")
    ax[0].legend(loc="best")
    k = 1
    if has_u:
        ax[k].plot(t, data["u"], lw=0.8)
        ax[k].set_ylabel("výstup u [V]")
        k += 1
    if has_i:
        for key, lab in (("i_q", "i_q"), ("i_d", "i_d")):
            if key in data and any(x == x for x in data[key]):
                ax[k].plot(t, data[key], lw=0.8, label=lab)
        ax[k].set_ylabel("prúd [A]")
        ax[k].legend(loc="best")
    ax[-1].set_xlabel("čas [s]")
    for a in ax:
        a.grid(True, alpha=0.3)
    fig.suptitle(os.path.basename(path))
    fig.tight_layout()
    out = os.path.splitext(path)[0] + ".png"
    fig.savefig(out, dpi=150)
    print(f"graf: {out}")
    if show:
        plt.show()


def plot(path, data, res, show):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = data["t_s"]
    fig, ax = plt.subplots(4, 1, sharex=True, figsize=(10, 9))
    ax[0].plot(t, data["ref_deg"], "k--", lw=1, label="žiadaná")
    ax[0].plot(t, data["theta_deg"], lw=1.2, label="skutočná")
    for m in res:
        if m.get("band_deg"):
            for y in (m["target_deg"] - m["band_deg"], m["target_deg"] + m["band_deg"]):
                ax[0].hlines(y, m["t0_s"], m["t0_s"] + m["duration_s"], colors="0.7", lw=0.6)
    ax[0].set_ylabel("poloha [°]")
    ax[0].legend(loc="best")
    ax[1].plot(t, data["err_deg"], lw=1)
    ax[1].set_ylabel("chyba [°]")
    ax[2].plot(t, data["speed_rpm"], lw=1)
    ax[2].set_ylabel("rýchlosť [rpm]")
    ax[3].plot(t, data["u"], lw=1)
    ax[3].set_ylabel("výstup u [V]")
    ax[3].set_xlabel("čas [s]")
    for a in ax:
        a.grid(True, alpha=0.3)
    fig.suptitle(os.path.basename(path))
    fig.tight_layout()
    out = os.path.splitext(path)[0] + ".png"
    fig.savefig(out, dpi=150)
    print(f"graf: {out}")
    if show:
        plt.show()


def main():
    p = argparse.ArgumentParser(description="Metriky a graf prechodovej charakteristiky polohy")
    p.add_argument("csv", nargs="+")
    p.add_argument("--band", type=float, default=5.0, help="pasmo ustalenia v %% skoku (2 alebo 5)")
    p.add_argument("--no-plot", action="store_true", help="len metriky, bez matplotlib")
    p.add_argument("--show", action="store_true", help="graf aj zobrazit v okne")
    args = p.parse_args()
    for path in args.csv:
        data = load_csv(path)
        speed = "ref_rpm" in data
        if speed:
            data, res = analyze_speed(data, args.band)
            print_speed_metrics(path, res, args.band)
        else:
            res = analyze(data, args.band)
            print_metrics(path, res, args.band)
        if not args.no_plot:
            try:
                (plot_speed if speed else plot)(path, data, res, args.show)
            except ImportError:
                print("matplotlib nie je nainstalovany (pip install matplotlib), graf sa nevytvori")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
