#!/usr/bin/env python3
"""Test rychlostneho servopohonu na jednom motore (bez siete): skoky ziadanej rychlosti, zaznam 2 kHz.

--mode voltage (predvolene): vlastny PI regulator rychlosti cez napatie ([speed_pi] v configu, beh 1 kHz).
--mode library: rezim Speed kniznice AMD (na porovnanie; 4. 11. 2026 nepouzitelny, pozri kd240sync/speed_test.py).
Zaznamenava sa ziadana a skutocna rychlost, poloha, vystup regulatora u a volitelne prud i_q/i_d (--dbg-div).
Profil: ziadana rychlost [ot/min]:trvanie [s]. Motor musi byt volny.

Pouzitie (na doske):
  ./scripts/run_speed_test.sh --steps 200:2,400:2,0:1.5 --out spd_pi.csv
  ./scripts/run_speed_test.sh --steps 200:2,400:2,0:1.5 --cog config/cogging_board2.csv --repeat 3 --out spd.csv
  ./scripts/run_speed_test.sh --mode library --steps 300:2,600:2,0:1.5 --dbg-div 10 --out spd_lib.csv
  python3 tools/test_speed_step.py --backend sim --steps 300:1,0:1
Vyhodnotenie na PC: python tools/plot_step_response.py spd.csv
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kd240sync import speed_test
from kd240sync.config import load
from kd240sync.motor import create as create_motor
from kd240sync.timing import try_realtime


def report(res, out):
    st = res["stats"]
    if not st["samples"]:
        return
    speed_test.write_csv(out, res["data"])
    print(f"Zapisane {st['samples']} vzoriek do {out}")
    print(f"Perioda vzorky: priemer {st['period_ms_mean']:.3f} ms, jitter priemer {st['mean_jitter_us']:.0f} us, "
          f"max {st['max_jitter_us']:.0f} us, vynechane cykly {st['overruns']}")
    print(f"citanie polohy a rychlosti: priemer {st['read_us_mean']:.0f} us, max {st['read_us_max']:.0f} us; "
          f"citanie prudu: priemer {st['dbg_us_mean']:.0f} us, max {st['dbg_us_max']:.0f} us")
    print(f"ignorovane chybne rychlosti z kniznice: {st['speed_glitches']}")


def main():
    p = argparse.ArgumentParser(description="Skokova odozva rychlostneho servopohonu, zaznam 2 kHz")
    p.add_argument("--steps", default="300:2,600:2,0:1.5", help="ziadana rychlost [ot/min]:trvanie [s], ciarkou")
    p.add_argument("--settle", type=float, default=0.5, help="cas na 0 ot/min pred prvym skokom [s]")
    p.add_argument("--sample-hz", type=float, default=2000.0)
    p.add_argument("--mode", choices=["voltage", "library"], default="voltage",
                   help="voltage = vlastny PI cez napatie, library = rezim Speed kniznice AMD")
    p.add_argument("--control-hz", type=float, default=1000.0, help="frekvencia regulatora v rezime voltage")
    p.add_argument("--kp", type=float, default=None, help="prepise speed_pi.kp_v_per_rpm")
    p.add_argument("--ki", type=float, default=None, help="prepise speed_pi.ki_v_per_rpm_s")
    p.add_argument("--kfc", type=float, default=None, help="prepise speed_pi.kfc_v (suche trenie)")
    p.add_argument("--cog", default=None, help="tabulka coggingu (rovnaka ako pri polohe)")
    p.add_argument("--dbg-div", type=int, default=0,
                   help="prud z kniznice citat kazdu N-tu vzorku, 0 = nie (jedno citanie trva ~0,5 ms)")
    p.add_argument("--max-rpm", type=float, default=None,
                   help="nad touto rychlostou motor vypnut (predvolene 1,25 x najvyssia v profile + 100); config "
                        "kniznice ma SPEED_SP=1000 a RST_SPEED=250, pri zapnuti rezimu moze motor kratko ist k nim")
    p.add_argument("--repeat", type=int, default=1, help="pocet opakovani; pri N > 1 subory <out>_1.csv az <out>_N.csv")
    p.add_argument("--pause", type=float, default=1.5, help="pauza medzi opakovaniami [s] (motor vypnuty, dobieha)")
    p.add_argument("--rt", action="store_true", help="SCHED_FIFO (vyzaduje root)")
    p.add_argument("--backend", choices=["foc_lib", "sim"], default="foc_lib")
    p.add_argument("--config", default=None)
    p.add_argument("--lib-config", default=None, help="Config kniznice AMD (napr. config/anaheim_torque.config)")
    p.add_argument("--out", default="speed_step.csv")
    args = p.parse_args()

    steps = speed_test.parse_steps(args.steps)
    top = max(abs(r) for r, _ in steps)
    if args.max_rpm is None:
        args.max_rpm = 1.25 * top + 100.0
    if top > args.max_rpm:
        print(f"Chyba: profil ide na {top:.0f} ot/min, nad --max-rpm {args.max_rpm:.0f}")
        return 1
    overrides = {"motor": {"backend": args.backend}, "speed_pi": {}}
    for key, val in (("kp_v_per_rpm", args.kp), ("ki_v_per_rpm_s", args.ki), ("kfc_v", args.kfc)):
        if val is not None:
            overrides["speed_pi"][key] = val
    if args.cog:
        overrides["speed_pi"]["cogging_table"] = os.path.abspath(args.cog)
    if args.lib_config:
        overrides["motor"]["foc_lib"] = {"config_path": os.path.abspath(args.lib_config)}
    cfg = load(args.config, overrides=overrides)

    if args.rt and not try_realtime():
        print("SCHED_FIFO sa nepodarilo nastavit (treba root)")
    motor = create_motor(cfg)
    motor.open()
    base, ext = os.path.splitext(args.out)
    faults = 0
    try:
        for k in range(max(1, args.repeat)):
            out = args.out if args.repeat <= 1 else f"{base}_{k + 1}{ext or '.csv'}"
            if args.repeat > 1:
                print(f"--- beh {k + 1}/{args.repeat}")
                if k:
                    time.sleep(args.pause)
            res = speed_test.run(cfg, motor, steps, args.sample_hz, args.settle, args.max_rpm, args.dbg_div,
                                 args.mode, args.control_hz)
            report(res, out)
            if res["fault"]:
                faults += 1
                break
    except KeyboardInterrupt:
        print("Prerusene")
        return 1
    finally:
        motor.stop()
        motor.close()
    return 2 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
