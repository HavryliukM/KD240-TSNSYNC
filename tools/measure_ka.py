#!/usr/bin/env python3
"""Automaticky nastroj na odmeranie konstanty Ka (zisk momentu k zrychleniu).

Fyzikalny princip:
  J * dw/dt = kt * I - tau_friction
  Pre nezatazeny motor:
  alpha = dw/dt = Ka * I - (tau_friction / J)
  Ka = kt / J  [rad/s^2 na 1 A]

Nastroj posle kratke bezpecne momentove pulzy (napr. 0.25 A na 250 ms),
zaznamena priebeh otacok s vysokou vzorkovacou frekvenciou
a vypocita zrychlenie alpha pomocou linearnej regresie.

Trenie sa odpocita meranim pri dvoch prudoch (I_hi a I_lo, obe v oboch smeroch):
  alpha_hi - alpha_lo = Ka * (I_hi - I_lo)
Rozdiel zrychleni nezavisi od trenia, preto Ka = (alpha_hi - alpha_lo) / (I_hi - I_lo).
Jednoprudove Ka = alpha_hi / I_hi sa vypisuje na porovnanie (je o trenie nizsie).

Pouzitie:
  # 1. Na doske KD240 s realnym motorom (vyzaduje sudo a nacitany firmver):
  sudo python3 tools/measure_ka.py

  # 2. Skuska v simulacii (na PC bez dosky):
  python3 tools/measure_ka.py --backend sim

  # 3. Vlastne nastavenie prudu a casu pulzu:
  sudo python3 tools/measure_ka.py --current 0.3 --duration 0.2
"""
import argparse
import math
import os
import signal
import sys
import time

# Pridaj koren projektu do sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kd240sync.config import load
from kd240sync.motor import create as create_motor
from kd240sync.motor.base import Motor

RPM_TO_RAD_S = 2.0 * math.pi / 60.0
MAX_SAFE_CURRENT_A = 0.5
MAX_SAFE_DURATION_S = 0.8
MIN_CURRENT_A = 0.05


def linear_regression(x_vals, y_vals):
    """Vypocita sklon (slope), posun (intercept) a koeficient determinacie R^2."""
    n = len(x_vals)
    if n < 3:
        return 0.0, 0.0, 0.0
    x_mean = sum(x_vals) / n
    y_mean = sum(y_vals) / n
    ss_xx = sum((x - x_mean) ** 2 for x in x_vals)
    ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
    ss_yy = sum((y - y_mean) ** 2 for y in y_vals)
    if ss_xx <= 1e-12:
        return 0.0, y_mean, 0.0
    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    r2 = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_yy > 1e-12 else 0.0
    return slope, intercept, r2


def run_single_pulse(motor: Motor, current_a: float, duration_s: float, max_rpm: float = 1500.0):
    """Vykona jeden kratky momentovy pulz a vrati zoznam (t_s, rpm, theta_deg)."""
    # Uisti sa, ze motor stoji
    motor.stop()
    t_settle = time.perf_counter()
    while time.perf_counter() - t_settle < 1.0:
        st = motor.read()
        if abs(st.speed_rpm) < 20.0:
            break
        time.sleep(0.05)

    samples = []
    t_start = time.perf_counter()
    try:
        motor.set_torque_a(current_a)
        while True:
            t_now = time.perf_counter()
            dt = t_now - t_start
            st = motor.read()
            samples.append((dt, st.speed_rpm, st.theta_deg))
            if dt >= duration_s or abs(st.speed_rpm) >= max_rpm:
                break
            time.sleep(0.001)
    finally:
        motor.stop()

    # Pockaj na bezpecne dobrzdenie
    time.sleep(0.4)
    return samples


def analyze_pulse(samples, current_a, duration_s):
    """Analyzuje namerane vzorky a vrati (alpha_rad_s2, r2, max_rpm, n_fit)."""
    if not samples:
        return 0.0, 0.0, 0.0, 0

    # Okno na linearnu regresiu:
    # preskocime prvych 20 ms (rozbeh prudu a filter kniznice)
    # a berieme data do konca pulzu
    t_min = 0.02
    t_max = duration_s * 0.95

    t_fit = []
    omega_fit = []
    max_rpm = 0.0

    for t, rpm, _ in samples:
        max_rpm = max(max_rpm, abs(rpm))
        if t_min <= t <= t_max:
            t_fit.append(t)
            omega_fit.append(rpm * RPM_TO_RAD_S)

    if len(t_fit) < 4:
        # Ak mame malo vzoriek v oknu, pouzijeme vsetky okrem prvej
        t_fit = [s[0] for s in samples[1:]]
        omega_fit = [s[1] * RPM_TO_RAD_S for s in samples[1:]]

    slope, intercept, r2 = linear_regression(t_fit, omega_fit)
    alpha = abs(slope)
    return alpha, r2, max_rpm, len(t_fit)


def main():
    parser = argparse.ArgumentParser(description="Automaticke odmeranie konstanty Ka motora")
    parser.add_argument("--backend", choices=["foc_lib", "sim"], default="foc_lib",
                        help="Backend motora (default: foc_lib)")
    parser.add_argument("--config", default=None, help="Cesta ku konfiguracnemu TOML suboru")
    parser.add_argument("--current", type=float, default=0.25,
                        help="Velkost testovacieho prudu [A] (default: 0.25 A, max 0.5 A)")
    parser.add_argument("--current-low", type=float, default=None,
                        help="Nizsi testovaci prud [A] pre odpocitanie trenia (default: polovica --current)")
    parser.add_argument("--duration", type=float, default=0.25,
                        help="Doba trvania pulzu [s] (default: 0.25 s, max 0.8 s)")
    parser.add_argument("--max-rpm", type=float, default=1500.0,
                        help="Bezpecnostny limit otacok pre prerusenie pulzu (default: 1500 RPM)")
    parser.add_argument("--trials", type=int, default=4,
                        help="Pocet pulzov na kazdu uroven prudu (strieda smery) (default: 4)")

    args = parser.parse_args()

    # Bezpecnostne kontroly argumentov
    if abs(args.current) > MAX_SAFE_CURRENT_A:
        print(f"Chyba: Zvoleny prud {args.current} A prekracuje bezpecnostny limit {MAX_SAFE_CURRENT_A} A!")
        return 1
    if args.duration > MAX_SAFE_DURATION_S:
        print(f"Chyba: Doba pulzu {args.duration} s prekracuje bezpecnostny limit {MAX_SAFE_DURATION_S} s!")
        return 1

    i_hi = abs(args.current)
    i_lo = abs(args.current_low) if args.current_low is not None else 0.5 * i_hi
    if i_lo < MIN_CURRENT_A or i_hi - i_lo < 0.3 * i_hi:
        print(f"Chyba: nizsi prud {i_lo:.3f} A musi byt aspon {MIN_CURRENT_A} A a o viac ako 30 % mensi nez {i_hi:.3f} A.")
        return 1

    print("=" * 68)
    print("           Automaticke meranie konstanty Ka (KD240 Sync)           ")
    print("=" * 68)
    print(f"Backend:           {args.backend}")
    print(f"Testovacie prudy:  {i_hi:.3f} A a {i_lo:.3f} A (odpocet trenia)")
    print(f"Dlzka pulzu:       {args.duration:.3f} s")
    print(f"Pocet pokusov:     {args.trials}")
    print(f"Bezpecnostny limit: {args.max_rpm:.0f} RPM")
    print("-" * 68)

    # Inicializacia motora
    overrides = {"motor": {"backend": args.backend}}
    cfg = load(args.config, overrides=overrides)

    try:
        motor = create_motor(cfg)
        motor.open()
    except Exception as err:
        print(f"\n[CHYBA] Nepodarilo sa otvorit motor ({args.backend}): {err}")
        if args.backend == "foc_lib":
            print("Uisti sa, ze:")
            print("  1. Skript bezi s pravami sudo (sudo python3 tools/measure_ka.py)")
            print("  2. Je nacitany firmver: sudo xmutil loadapp kd240-motor-ctrl-qei")
            print("  3. 24 V napajanie motora je zapnute.")
            print("  4. Pre test bez dosky pouzi: python3 tools/measure_ka.py --backend sim")
        return 1

    # Zachytenie Ctrl+C pre okamzite bezpecne zastavenie
    def _sig_handler(sig, frame):
        print("\n\n[STOP] Prerusene pouzivatelom! Zastavujem motor...")
        try:
            motor.stop()
            motor.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    results = []

    print("\nSpustam meracie pulzy (motor sa na zlomok sekundy kratko pootoci)...")
    print(f"{'Pokus':>5} | {'Smer/Prud [A]':>14} | {'Max RPM':>9} | {'Alfa [rad/s^2]':>15} | {'R^2':>6} | {'Alfa/I [rad/s^2/A]':>18}")
    print("-" * 78)

    try:
        n = 0
        for i in range(args.trials):
            # Striedame smer: +, -, +, -, ... a v kazdom smere oba prudy
            sign = 1.0 if (i % 2 == 0) else -1.0
            for level, mag in (("hi", i_hi), ("lo", i_lo)):
                n += 1
                test_i = sign * mag

                samples = run_single_pulse(motor, test_i, args.duration, max_rpm=args.max_rpm)
                alpha, r2, max_rpm, n_fit = analyze_pulse(samples, test_i, args.duration)

                results.append({
                    "trial": n,
                    "level": level,
                    "current": test_i,
                    "max_rpm": max_rpm,
                    "alpha": alpha,
                    "r2": r2,
                })

                print(f"{n:5d} | {test_i:+14.3f} | {max_rpm:9.1f} | {alpha:15.1f} | {r2:6.3f} | {alpha / mag:18.1f}")
                time.sleep(0.3)

    finally:
        motor.stop()
        motor.close()

    # Vyhodnotenie: priemer alfa pre kazdu uroven prudu cez oba smery, potom rozdiel
    alphas = {lvl: [r["alpha"] for r in results if r["level"] == lvl and r["r2"] >= 0.85 and r["alpha"] > 0.0]
              for lvl in ("hi", "lo")}

    print("=" * 78)
    if not alphas["hi"] or not alphas["lo"]:
        print("[VAROVANIE] Namerane hodnoty mali nizku kvalitu regresie (R^2 < 0.85) aspon pri jednom prude.")
        print("Mozne priciny: motor sa netocil (skontroluj 24V napajanie), alebo bol prud prilis maly.")
        print("Ak sa pri nizsom prude motor netoci (suche trenie), zvys --current-low.")
    else:
        def mean_sd(v):
            m = sum(v) / len(v)
            return m, math.sqrt(sum((x - m) ** 2 for x in v) / len(v))

        a_hi, sd_hi = mean_sd(alphas["hi"])
        a_lo, sd_lo = mean_sd(alphas["lo"])
        avg_ka = (a_hi - a_lo) / (i_hi - i_lo)
        std_ka = math.hypot(sd_hi, sd_lo) / (i_hi - i_lo)
        ka_single = a_hi / i_hi
        decel_friction = avg_ka * i_hi - a_hi       # spomalenie od trenia [rad/s^2]

        print("VYSLEDOK MERANIA:")
        print(f"  Platne pulzy:           {len(alphas['hi'])} z {args.trials} pri {i_hi:.3f} A, "
              f"{len(alphas['lo'])} z {args.trials} pri {i_lo:.3f} A")
        print(f"  Priemerna alfa:         {a_hi:.1f} rad/s^2 pri {i_hi:.3f} A, {a_lo:.1f} rad/s^2 pri {i_lo:.3f} A")
        print(f"  Odmerane Ka:            {avg_ka:.1f} +- {std_ka:.1f} rad/s^2/A (rozdielova metoda)")
        print(f"  Ka z jedneho prudu:     {ka_single:.1f} rad/s^2/A (zahrna trenie, podhodnotene o {(1 - ka_single / avg_ka) * 100.0:.1f} %)")
        print(f"  Odhad trenia:           {decel_friction:.1f} rad/s^2")
        print(f"  Predvolena hodnota:     2500.0 rad/s^2/A")
        print(f"  Odchylka od modelu:     {((avg_ka - 2500.0) / 2500.0) * 100.0:+.1f} %")
        if avg_ka <= 0.0 or decel_friction < 0.0:
            print("[VAROVANIE] Zaporne trenie alebo Ka alebo velky rozptyl: vysledok je nespolahlivy, zopakuj meranie.")
        print("-" * 78)
        print("ODPORUCANY ZAPIS DO KONFIGURACNYCH SUBOROV:")
        print("Tuto hodnotu zapis do config/board1.toml (alebo board2.toml):")
        print()
        print("  [safety]")
        print(f"  ka_rad_s2_per_a = {round(avg_ka, 1)}")
        print()
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

