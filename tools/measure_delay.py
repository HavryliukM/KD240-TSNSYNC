#!/usr/bin/env python3
"""Zmeria mrtvy cas medzi prikazom momentu a reakciou motora (skok z pokoja).

Pre kazdy pokus: motor stoji, v case 0 sa nastavi prud, 0.4 s sa vzorkuje poloha a rychlost.
Vypise:
  t_theta  - cas, kedy sa poloha zmenila o aspon 3 stupne od startu
  t_speed  - cas, kedy hlasena rychlost prekrocila 15 rpm
  t_dtheta - cas, kedy rychlost z derivacie polohy (okno 10 ms) prekrocila 90 deg/s
Ak je t_speed alebo t_dtheta o desiatky ms dlhsie nez t_theta, oneskoruje sa odpoved motora
(moment). Ak sa t_speed a t_dtheta lisia, oneskoruje sa jedno z cítani.

Pouzitie (na doske, motor volny):
  ./scripts/run_measure_delay.sh --lib-config config/anaheim_torque.config
  python3 tools/measure_delay.py --backend sim
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kd240sync.angle import Unwrapper
from kd240sync.config import load
from kd240sync.motor import create as create_motor

MAX_CURRENT_A = 0.3
MAX_RPM = 600.0


def first_time(samples, pred):
    for s in samples:
        if pred(s):
            return s[0]
    return None


def one_trial(motor, current_a, duration_s):
    motor.stop()
    time.sleep(0.5)
    unw = Unwrapper()
    st = motor.read()
    theta0 = unw.update(st.theta_deg)
    samples = []                       # (t, theta_rel, rpm)
    t0 = time.perf_counter()
    motor.set_torque_a(current_a)
    try:
        while True:
            t = time.perf_counter() - t0
            st = motor.read()
            samples.append((t, unw.update(st.theta_deg) - theta0, st.speed_rpm))
            if t >= duration_s or abs(st.speed_rpm) >= MAX_RPM:
                break
            time.sleep(0.001)
    finally:
        motor.stop()
    return samples


def main():
    p = argparse.ArgumentParser(description="Mrtvy cas motora po prikaze momentu")
    p.add_argument("--backend", choices=["foc_lib", "sim"], default="foc_lib")
    p.add_argument("--config", default=None)
    p.add_argument("--lib-config", default=None, help="Config kniznice AMD (anaheim_torque.config)")
    p.add_argument("--current", type=float, default=0.2, help="Prud skoku [A] (max 0.3)")
    p.add_argument("--trials", type=int, default=4)
    p.add_argument("--duration", type=float, default=0.4)
    args = p.parse_args()

    if abs(args.current) > MAX_CURRENT_A:
        print(f"Chyba: prud {args.current} A prekracuje limit {MAX_CURRENT_A} A")
        return 1

    overrides = {"motor": {"backend": args.backend}}
    if args.lib_config:
        overrides["motor"]["foc_lib"] = {"config_path": os.path.abspath(args.lib_config)}
    motor = create_motor(load(args.config, overrides=overrides))
    motor.open()

    print(f"Skok {args.current:+.3f} A z pokoja, {args.trials} pokusov (striedaju sa smery)")
    print(f"{'Pokus':>5} | {'Prud':>7} | {'t_theta':>8} | {'t_speed':>8} | {'t_dtheta':>8} | {'periodu vzorky':>14}")
    print("-" * 66)
    try:
        for i in range(args.trials):
            cur = args.current if i % 2 == 0 else -args.current
            s = one_trial(motor, cur, args.duration)
            sg = 1.0 if cur > 0 else -1.0
            t_theta = first_time(s, lambda x: sg * x[1] >= 3.0)
            t_speed = first_time(s, lambda x: sg * x[2] >= 15.0)
            # rychlost z derivacie polohy cez okno 10 ms
            t_dth = None
            for k in range(len(s)):
                j = k
                while j > 0 and s[k][0] - s[j][0] < 0.010:
                    j -= 1
                dt = s[k][0] - s[j][0]
                if dt >= 0.008 and sg * (s[k][1] - s[j][1]) / dt >= 90.0:
                    t_dth = s[k][0]
                    break
            period = (s[-1][0] - s[0][0]) / max(1, len(s) - 1)

            def f(v):
                return f"{v * 1e3:6.0f} ms" if v is not None else "   --    "
            print(f"{i + 1:5d} | {cur:+7.3f} | {f(t_theta):>8} | {f(t_speed):>8} | {f(t_dth):>8} | {period * 1e3:11.2f} ms")
            if i == 0:
                print("      priebeh 1. pokusu (t [ms], poloha [deg], rpm), kazdych ~20 ms:")
                last = -1.0
                for t, th, rpm in s:
                    if t - last >= 0.020:
                        print(f"        {t * 1e3:6.0f}  {th:8.1f}  {rpm:7.1f}")
                        last = t
            time.sleep(0.5)
    finally:
        motor.stop()
        motor.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
