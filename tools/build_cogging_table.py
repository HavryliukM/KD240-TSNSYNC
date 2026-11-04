#!/usr/bin/env python3
"""Vytvori tabulku kompenzacie coggingu z CSV pomalej rampy (tools/test_position_step.py so stlpcom raw_deg).

Rampa musi prejst celu otacku hore aj dole, napriklad:
  ./scripts/run_position_test.sh --steps 360:10,0:10 --ramp-dps 45 --kfc 0.10 --rt --out ramp360.csv
Potom (na PC alebo na doske):
  python tools/build_cogging_table.py ramp360.csv --out config/cogging_board2.csv
  python tools/build_cogging_table.py a.csv b.csv --out config/cogging_board2.csv   # priemer viacerych behov
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kd240sync import cogging
from kd240sync.step_metrics import load_csv


def main():
    p = argparse.ArgumentParser(description="Tabulka coggingu z rampy cez celu otacku")
    p.add_argument("csv", nargs="+")
    p.add_argument("--out", required=True, help="vystupna tabulka (CSV angle_deg,u)")
    p.add_argument("--bins", type=int, default=360)
    p.add_argument("--smooth", type=int, default=5, help="kruhovy kĺzavy priemer cez N binov (neparne)")
    p.add_argument("--plot", action="store_true", help="ulozit PNG tabulky vedla vystupu (matplotlib)")
    args = p.parse_args()

    tables, frics = [], []
    for path in args.csv:
        data = load_csv(path)
        if "raw_deg" not in data:
            print(f"{path}: chyba stlpec raw_deg (stara verzia nastroja), preskakujem")
            continue
        t, fric, cover = cogging.build(data, args.bins, args.smooth)
        tables.append(t)
        frics.append(fric)
        print(f"{path}: pokrytie {cover * 100:.0f} %, trenie {fric:.3f} V, "
              f"cogging {min(t.values):+.3f} az {max(t.values):+.3f} V")
    if not tables:
        return 1
    vals = [sum(t.values[i] for t in tables) / len(tables) for i in range(args.bins)]
    if len(tables) > 1:
        dev = max(abs(t.values[i] - vals[i]) for t in tables for i in range(args.bins))
        print(f"najvacsia odchylka behu od priemeru: {dev:.3f} V (opakovatelnost)")
    table = cogging.CoggingTable(vals)
    table.save(args.out)
    print(f"tabulka: {args.out} ({args.bins} binov), odporucane kfc_v = {sum(frics) / len(frics):.3f} V")
    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        x = [i * 360.0 / args.bins for i in range(args.bins)]
        fig, ax = plt.subplots(figsize=(10, 3.5))
        for t, path in zip(tables, args.csv):
            ax.plot(x, t.values, lw=0.7, alpha=0.6, label=os.path.basename(path))
        ax.plot(x, vals, "k", lw=1.2, label="tabulka")
        ax.set_xlabel("uhol z kniznice [deg]")
        ax.set_ylabel("u [V]")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        png = os.path.splitext(args.out)[0] + ".png"
        fig.savefig(png, dpi=120)
        print(f"graf: {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
