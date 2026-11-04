#!/usr/bin/env python3
"""Test polohoveho servopohonu na jednom motore (bez siete): skoky alebo rampy polohy, zaznam 1 kHz do CSV.

Poloha je relativna od startu (0 deg = kde motor stoji pri spusteni). Profil: cielova poloha:drzanie [s].
Skok 90 deg pri limite 1 V nasyti vystup, preto zacni malymi skokmi (10 az 30 deg) a motor nechaj volny.

Pouzitie (na doske):
  ./scripts/run_position_test.sh --steps 20:2,0:2
  ./scripts/run_position_test.sh --steps 90:2,180:2,0:2 --ramp-dps 360
  python3 tools/test_position_step.py --backend sim --steps 30:1,0:1 --out step.csv
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kd240sync import position_test
from kd240sync.config import load
from kd240sync.motor import create as create_motor
from kd240sync.timing import try_realtime


def main():
    p = argparse.ArgumentParser(description="Skokova odozva polohoveho servopohonu (voltage_pd), zaznam 1 kHz")
    p.add_argument("--steps", default="20:2,0:2", help="cielova poloha [deg]:drzanie [s], oddelene ciarkou")
    p.add_argument("--ramp-dps", type=float, default=0.0, help="rychlost rampy [deg/s], 0 = skok")
    p.add_argument("--settle", type=float, default=0.5, help="drzanie na 0 deg pred prvym krokom [s]")
    p.add_argument("--sample-hz", type=float, default=1000.0, help="vzorkovacia frekvencia zaznamu")
    p.add_argument("--control-hz", type=float, default=None, help="frekvencia regulatora (predvolene receiver.rate_hz)")
    p.add_argument("--max-rpm", type=float, default=600.0, help="nad touto rychlostou FAULT")
    p.add_argument("--max-error", type=float, default=None, help="limit chyby [deg] (predvolene najvacsi skok + 30)")
    p.add_argument("--spin-us", type=float, default=0.0, help="aktivne cakanie na termin vzorky [us]")
    p.add_argument("--kfc", type=float, default=None, help="kompenzacia trenia [V] (prepise receiver.voltage_pd.kfc_v)")
    p.add_argument("--cog", default=None, help="tabulka coggingu (tools/build_cogging_table.py)")
    p.add_argument("--cog-gain", type=float, default=None, help="nasobok tabulky coggingu (napr. 0.5)")
    p.add_argument("--rt", action="store_true", help="SCHED_FIFO (vyzaduje root)")
    p.add_argument("--backend", choices=["foc_lib", "sim"], default="foc_lib")
    p.add_argument("--config", default=None)
    p.add_argument("--lib-config", default=None, help="Config kniznice AMD (anaheim_torque.config)")
    p.add_argument("--out", default="position_step.csv")
    p.add_argument("--repeat", type=int, default=1,
                   help="pocet opakovani profilu; pri N > 1 sa uklada ako <out>_1.csv az <out>_N.csv")
    p.add_argument("--pause", type=float, default=1.0, help="pauza medzi opakovaniami [s] (motor vypnuty)")
    args = p.parse_args()

    overrides = {"motor": {"backend": args.backend}, "receiver": {"mode": "voltage_pd"}}
    if args.lib_config:
        overrides["motor"]["foc_lib"] = {"config_path": os.path.abspath(args.lib_config)}
    vp = overrides["receiver"]["voltage_pd"] = {}
    if args.kfc is not None:
        vp["kfc_v"] = args.kfc
    if args.cog:
        vp["cogging_table"] = os.path.abspath(args.cog)
    if args.cog_gain is not None:
        vp["cogging_gain"] = args.cog_gain
    cfg = load(args.config, overrides=overrides)
    steps = position_test.parse_steps(args.steps)

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
            res = position_test.run(cfg, motor, steps, args.sample_hz, args.control_hz, args.ramp_dps,
                                    args.settle, args.max_error, args.max_rpm, args.spin_us)
            report(res, out)
            if res["fault"]:
                faults += 1
                break                                   # po FAULT dalsie behy nespustat
    except KeyboardInterrupt:
        print("\nPrerusene")
        return 1
    finally:
        motor.stop()
        motor.close()
    return 2 if faults else 0


def report(res, out):
    st = res["stats"]
    if not st["samples"]:
        return
    position_test.write_csv(out, res["data"])
    print(f"Zapisane {st['samples']} vzoriek do {out}")
    print(f"Perioda vzorky: priemer {st['period_ms_mean']:.3f} ms, jitter priemer {st['mean_jitter_us']:.0f} us, "
          f"max {st['max_jitter_us']:.0f} us, vynechane cykly {st['overruns']}")
    print(f"motor.read(): priemer {st['read_us_mean']:.0f} us, p99 {st['read_us_p99']:.0f} us, "
          f"max {st['read_us_max']:.0f} us")
    print(f"Chyba polohy RMS {st['err_rms_deg']:.2f} deg, ignorovane chybne rychlosti z kniznice: "
          f"{st['speed_glitches']}")


if __name__ == "__main__":
    raise SystemExit(main())
