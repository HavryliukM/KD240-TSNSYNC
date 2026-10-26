#!/usr/bin/env python3
"""Vyhodnotenie CSV logu receivera (receiver.log_path). Len standardna kniznica.

Pouzitie: python3 tools/analyze_log.py receiver_log.csv
"""
import csv
import math
import statistics as st
import sys


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(p / 100 * len(v)))] if v else float("nan")


def main(path):
    err, age, lat, out = [], [], [], []
    with open(path) as f:
        for r in csv.DictReader(f):
            if r["state"] != "RUN":
                continue
            err.append(float(r["err_deg"]))
            age.append(float(r["age_ms"]))
            out.append(float(r["output"]))
            x = float(r["lat_ms"])
            if not math.isnan(x):
                lat.append(x)
    if not err:
        print("ziadne riadky v stave RUN")
        return 1
    a = [abs(x) for x in err]
    print(f"vzoriek: {len(err)}")
    print(f"chyba polohy [deg]: rms={math.sqrt(st.fmean(x*x for x in err)):.3f} "
          f"max={max(a):.2f} p95={pct(a, 95):.2f} p99={pct(a, 99):.2f} priemer={st.fmean(err):+.3f}")
    print(f"vek paketu [ms]:    priemer={st.fmean(age):.2f} max={max(age):.2f}")
    if lat:
        print(f"jednosmerne oneskorenie [ms] (len pri synchronizovanych hodinach): "
              f"min={min(lat):.3f} priemer={st.fmean(lat):.3f} p99={pct(lat, 99):.3f} max={max(lat):.3f}")
    print(f"vystup regulatora:  min={min(out):+.3f} max={max(out):+.3f}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
