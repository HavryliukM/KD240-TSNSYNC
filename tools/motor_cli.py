#!/usr/bin/env python3
"""Samostatny nastroj na priame ovladanie a monitorovanie motora na doske KD240.

Umoznuje ovladat motor z prikazoveho riadku BEZ spusteneho Bokeh dashboardu.

Pouzitie:
  # 1. Interaktivny rezim (odporucany):
  sudo python3 tools/motor_cli.py

  # 2. Len monitorovanie polohy a otacok (napr. pri rucnom otacani):
  sudo python3 tools/motor_cli.py --monitor

  # 3. Rozbeh na zadane otacky na 5 sekund:
  sudo python3 tools/motor_cli.py --speed 500 --duration 5

  # 4. Skuska momentoveho riadenia (maly prud 0.1 A):
  sudo python3 tools/motor_cli.py --torque 0.1 --duration 3

  # 5. Okamzite bezpecne zastavenie motora (rezim Off):
  sudo python3 tools/motor_cli.py --stop

  # 6. Vymazanie poruch (faults):
  sudo python3 tools/motor_cli.py --clear-faults

  # Test v simulacii (na PC bez dosky):
  python3 tools/motor_cli.py --backend sim
"""
import argparse
import os
import signal
import sys
import time

# Pridaj koren projektu do sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from kd240sync.angle import Unwrapper
from kd240sync.config import load
from kd240sync.motor import create as create_motor
from kd240sync.motor.base import Motor

# Bezpecnostne limity
MAX_ALLOWED_RPM = 3000.0
MAX_ALLOWED_TORQUE_A = 1.0


def print_banner():
    print("=" * 65)
    print("       KD240 Standalone Motor Control CLI (Direct Control)       ")
    print("=" * 65)


def monitor_loop(motor: Motor, interval_s=0.1):
    print("\n--- Monitorovanie motora (Ctrl+C pre navrat/ukoncenie) ---")
    print(f"{'Cas [s]':>8} | {'Uhol [deg]':>10} | {'Otacky [RPM]':>12}")
    print("-" * 38)
    t0 = time.monotonic()
    try:
        while True:
            st = motor.read()
            elapsed = time.monotonic() - t0
            print(f"{elapsed:8.2f} | {st.theta_deg:10.2f} | {st.speed_rpm:12.1f}", end="\r")
            time.sleep(interval_s)
    except KeyboardInterrupt:
        print("\nMonitorovanie ukoncene.")


def _run_timed(motor: Motor, duration_s: float, label: str, sample_s=0.02, print_s=0.25):
    """Vzorkuje motor a kazdych print_s vypise novy riadok; uhol sa rozvija (bez skoku 360 -> 0).

    Pri 270 rpm by 100 ms vzorkovanie uz skreslilo uhol, preto sa vzorkuje rychlejsie nez sa vypisuje.
    """
    unw = Unwrapper()
    t0 = time.monotonic()
    t_print = 0.0
    theta0 = None
    while True:
        st = motor.read()
        t = time.monotonic() - t0
        total = unw.update(st.theta_deg)
        if theta0 is None:
            theta0 = total
        if t >= t_print:
            print(f"{t:5.2f} s | {label} | Otacky: {st.speed_rpm:7.1f} RPM | "
                  f"Uhol: {st.theta_deg:6.1f}° | Od startu: {total - theta0:+9.1f}°")
            t_print += print_s
        if t >= duration_s:
            break
        time.sleep(sample_s)


def run_speed(motor: Motor, rpm: float, duration_s: float):
    if abs(rpm) > MAX_ALLOWED_RPM:
        print(f"Chyba: Pozadovane otacky {rpm} prekracuju bezpecnostny limit {MAX_ALLOWED_RPM} RPM!")
        return

    print(f"\n[START] Rezim Rychlost: Nastavujem {rpm:.1f} RPM na {duration_s:.1f} s...")
    motor.set_speed_rpm(rpm)
    try:
        _run_timed(motor, duration_s, f"Ziadana: {rpm:6.0f} RPM")
    except KeyboardInterrupt:
        print("\nPrerusene pouzivatelom (Ctrl+C).")
    finally:
        motor.stop()
        print("\n[STOP] Motor zastaveny (rezim Off).")


def run_torque(motor: Motor, amps: float, duration_s: float):
    if abs(amps) > MAX_ALLOWED_TORQUE_A:
        print(f"Chyba: Pozadovany prud {amps} A prekracuje bezpecnostny limit {MAX_ALLOWED_TORQUE_A} A!")
        return

    print(f"\n[START] Rezim Moment: Nastavujem {amps:+.3f} A na {duration_s:.1f} s...")
    motor.set_torque_a(amps)
    try:
        _run_timed(motor, duration_s, f"Moment: {amps:+.3f} A")
    except KeyboardInterrupt:
        print("\nPrerusene pouzivatelom (Ctrl+C).")
    finally:
        motor.stop()
        print("\n[STOP] Motor zastaveny (rezim Off).")


def interactive_menu(motor: Motor):
    print_banner()
    print("Dostupne prikazy:")
    print("  s <rpm>    - zapnutie regulacie rychlosti (napr. 's 500' alebo 's -300')")
    print("  t <amps>   - zapnutie momentu/prudu (napr. 't 0.1' alebo 't -0.15')")
    print("  m          - spustit zive monitorovanie stavu")
    print("  c          - vymazat poruchy (clear faults)")
    print("  stop       - uvolnit motor (rezim Off / volnobeh)")
    print("  q          - ukoncit program")
    print("-" * 65)

    while True:
        try:
            line = input("\n[motor_cli] Zadaj prikaz: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nUkoncujem...")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("q", "quit", "exit"):
            break
        elif cmd == "stop":
            motor.stop()
            print("Motor uvolneny (rezim Off).")
        elif cmd == "c":
            if hasattr(motor, "clear_faults"):
                motor.clear_faults()
                print("Poruchy vymazane (clearFaults zavolane).")
            else:
                print("Tento backend nepodporuje clear_faults.")
        elif cmd == "m":
            monitor_loop(motor)
        elif cmd == "s":
            if len(parts) < 2:
                print("Pouzitie: s <rpm>  (napr. s 500)")
                continue
            try:
                target_rpm = float(parts[1])
            except ValueError:
                print("Chyba: RPM musi byt cislo!")
                continue
            if abs(target_rpm) > MAX_ALLOWED_RPM:
                print(f"Chyba: RPM nad povoleny limit {MAX_ALLOWED_RPM}!")
                continue
            motor.set_speed_rpm(target_rpm)
            print(f"Rychlost nastavena na {target_rpm} RPM. (Zadaj 'stop' pre zastavenie)")
        elif cmd == "t":
            if len(parts) < 2:
                print("Pouzitie: t <amps>  (napr. t 0.1)")
                continue
            try:
                target_a = float(parts[1])
            except ValueError:
                print("Chyba: Prud musi byt cislo!")
                continue
            if abs(target_a) > MAX_ALLOWED_TORQUE_A:
                print(f"Chyba: Prud nad povoleny limit {MAX_ALLOWED_TORQUE_A} A!")
                continue
            motor.set_torque_a(target_a)
            print(f"Moment nastaveny na {target_a} A. (Zadaj 'stop' pre zastavenie)")
        else:
            print("Neznamy prikaz. Prikazy: s <rpm>, t <amps>, m, c, stop, q")


def main():
    parser = argparse.ArgumentParser(description="KD240 Standalone Motor Control CLI")
    parser.add_argument("--backend", choices=["foc_lib", "sim", "iio_readonly"], default="foc_lib",
                        help="Backend motora (default: foc_lib)")
    parser.add_argument("--config", default=None, help="Cesta ku konfiguracnemu toml suboru")
    parser.add_argument("--speed", type=float, default=None, help="Spustit na zadane otacky [RPM]")
    parser.add_argument("--torque", type=float, default=None, help="Spustit na zadany moment [A]")
    parser.add_argument("--duration", type=float, default=5.0, help="Doba behu v sekundach (default: 5.0 s)")
    parser.add_argument("--monitor", action="store_true", help="Iba monitorovat polohu a rychlost")
    parser.add_argument("--stop", action="store_true", help="Okamzite zastavit motor")
    parser.add_argument("--clear-faults", action="store_true", help="Vymazat poruchy v kniznici")

    args = parser.parse_args()

    # Priprava konfiguracie
    overrides = {"motor": {"backend": args.backend}}
    cfg = load(args.config, overrides=overrides)

    try:
        motor = create_motor(cfg)
    except Exception as err:
        print(f"Chyba pri vytvarani motora ({args.backend}): {err}")
        return 1

    print(f"Otvaram motor (backend: {args.backend})...")
    try:
        motor.open()
    except Exception as err:
        print(f"Chyba pri inicializacii motora: {err}")
        if args.backend == "foc_lib":
            print("\nTip: Ak testujes na PC bez dosky KD240, pouzi: python3 tools/motor_cli.py --backend sim")
            print("Tip: Na doske KD240 sa uisti, ze je nacitany firmver:")
            print("     sudo xmutil loadapp kd240-motor-ctrl-qei")
        return 1

    # Zachytenie signalov pre bezpecne zastavenie
    def _sig_handler(sig, frame):
        print("\nZachyneny signal na ukoncenie -> zastavujem motor...")
        try:
            motor.stop()
            motor.close()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    try:
        if args.stop:
            motor.stop()
            print("Motor bol uvedeny do stavu kModeOff (volnobeh).")
            return 0

        if args.clear_faults:
            if hasattr(motor, "clear_faults"):
                motor.clear_faults()
                print("clearFaults() vykonane.")
            else:
                print("Backend nepodporuje clear_faults.")
            return 0

        if args.monitor:
            monitor_loop(motor)
            return 0

        if args.speed is not None:
            run_speed(motor, args.speed, args.duration)
            return 0

        if args.torque is not None:
            run_torque(motor, args.torque, args.duration)
            return 0

        # Ak neboli zadane ziadne prepinace, spusti interaktivne menu
        interactive_menu(motor)

    finally:
        try:
            motor.stop()
        except Exception:
            pass
        try:
            motor.close()
        except Exception:
            pass
        print("Motor bezpecne odpojeny.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
