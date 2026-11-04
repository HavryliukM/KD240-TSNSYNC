#!/usr/bin/env python3
"""Ako casto kniznica AMD naozaj meni polohu a rychlost (z CSV tools/test_position_step.py).

Ak vzorkujeme rychlejsie, nez kniznica hodnotu obnovuje, ta ista hodnota sa opakuje vo viacerych vzorkach.
Najkratsi typicky interval medzi zmenami (pocas pohybu) je teda perioda obnovovania v kniznici; vzorkovat
rychlejsie uz neprinesie nove udaje. Poloha sa pocas pohybu meni aspon o 1 deg (rozlisenie), preto treba
pohyb dost rychly, aby sa 1 deg zmenil castejsie, nez je perioda obnovovania (napr. 240 ot/min = 1 deg za 0,7 ms).

Pouzitie:
  python tools/update_rate.py rate2k.csv
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kd240sync.step_metrics import load_csv


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p / 100 * len(v)))] if v else float("nan")


def change_intervals(t, vals, mask):
    """Casy [s] medzi po sebe iducimi zmenami hodnoty, len v useku, kde plati mask."""
    out, last = [], None
    for i in range(1, len(t)):
        if not mask[i]:
            last = None
            continue
        if vals[i] != vals[i - 1]:
            if last is not None:
                out.append(t[i] - last)
            last = t[i]
    return out


def analyze(data, min_rpm=30.0):
    t = data["t_s"]
    dt = sorted(t[i] - t[i - 1] for i in range(1, len(t)))[len(t) // 2]
    moving = [abs(v) >= min_rpm for v in data["speed_rpm"]]
    res = {"dt_ms": dt * 1e3, "moving_samples": sum(moving)}
    for col in ("raw_deg", "speed_rpm"):
        if col not in data:
            continue
        iv = change_intervals(t, data[col], moving)
        same = sum(1 for i in range(1, len(t)) if moving[i] and data[col][i] == data[col][i - 1])
        res[col] = {"changes": len(iv), "repeat_frac": same / max(1, sum(moving)),
                    "p10_ms": pct(iv, 10) * 1e3, "median_ms": pct(iv, 50) * 1e3, "p90_ms": pct(iv, 90) * 1e3}
    if "raw_deg" in data:
        jumps = [abs((data["raw_deg"][i] - data["raw_deg"][i - 1] + 180.0) % 360.0 - 180.0)
                 for i in range(1, len(t)) if moving[i] and data["raw_deg"][i] != data["raw_deg"][i - 1]]
        res["raw_deg"]["median_jump_deg"] = pct(jumps, 50)
    return res


def main():
    p = argparse.ArgumentParser(description="Perioda obnovovania polohy a rychlosti v kniznici")
    p.add_argument("csv", nargs="+")
    p.add_argument("--min-rpm", type=float, default=30.0, help="vyhodnocuje sa len pohyb nad touto rychlostou")
    args = p.parse_args()
    for path in args.csv:
        r = analyze(load_csv(path), args.min_rpm)
        print(f"\n{path}: perioda vzorky {r['dt_ms']:.3f} ms, vzoriek v pohybe {r['moving_samples']}")
        for col, name in (("raw_deg", "poloha"), ("speed_rpm", "rychlost")):
            if col not in r:
                continue
            c = r[col]
            extra = f", typicky skok {c['median_jump_deg']:.0f} deg" if "median_jump_deg" in c else ""
            print(f"  {name:8s}: zmien {c['changes']:5d}, opakovana hodnota v {c['repeat_frac'] * 100:4.0f} % vzoriek, "
                  f"interval medzi zmenami p10 {c['p10_ms']:.2f} / median {c['median_ms']:.2f} / "
                  f"p90 {c['p90_ms']:.2f} ms{extra}")
    print("\nNajkratsi typicky interval (p10) pri dostatocne rychlom pohybe ~ perioda obnovovania v kniznici.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
