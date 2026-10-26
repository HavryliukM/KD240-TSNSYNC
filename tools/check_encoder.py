#!/usr/bin/env python3
"""Zisti, ci enkoder reaguje cez IIO sysfs (zariadenie hls_qei_axi).

Pouzitie:  python3 tools/check_encoder.py [sekundy]   (default 20)
Pocas behu otacaj hriadelom motora rukou (motor v rezime Off) a sleduj, ci sa
hodnoty menia. Ak raw ostava 0, kym dashboard polohu ukazuje, cez sysfs sa pozicia
neda citat a treba pouzit motorovu kniznicu.
"""
import glob
import os
import sys
import time

ROOT = "/sys/bus/iio/devices"


def find(name="hls_qei_axi"):
    for d in sorted(glob.glob(os.path.join(ROOT, "iio:device*"))):
        try:
            if open(os.path.join(d, "name")).read().strip() == name:
                return d
        except OSError:
            pass
    return None


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    dev = find()
    if not dev:
        print("zariadenie hls_qei_axi nenajdene - je nacitany firmware kd240-motor-ctrl-qei?")
        return 1
    print("zariadenie:", dev)
    print("subory:", ", ".join(sorted(os.listdir(dev))))
    raws = sorted(glob.glob(os.path.join(dev, "in_*_raw")))
    if not raws:
        print("nenasli sa subory in_*_raw")
        return 1
    print("sledujem:", ", ".join(os.path.basename(r) for r in raws))
    last = None
    t_end = time.time() + secs
    while time.time() < t_end:
        vals = []
        for r in raws:
            try:
                vals.append(open(r).read().strip())
            except OSError as e:
                vals.append(f"chyba:{e.errno}")
        if vals != last:
            print(time.strftime("%H:%M:%S"), dict(zip((os.path.basename(r) for r in raws), vals)))
            last = vals
        time.sleep(0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
