"""Doska 1: riadi rychlost motora a posiela rozvinuty uhol a rychlost doske 2.

sender.mode = "library": rezim Speed kniznice AMD (4. 11. 2026 trvala odchylka 50 az 80 %, zmeny v tikoch po 0,5 s).
sender.mode = "voltage_pi": vlastny regulator rychlosti cez napatie (controller.SpeedPI, sekcia [speed_pi]).
"""
import csv
import queue
import sys
import threading
import time

from . import cogging, protocol, safety
from .angle import Unwrapper
from .controller import RampLimiter, SpeedPI
from .timing import PeriodicLoop


def stdin_commands(q: "queue.SimpleQueue", stop_event: threading.Event):
    """Cita prikazy z terminalu: 'rpm 500', 'stop', 'quit'."""
    for line in sys.stdin:
        parts = line.split()
        if not parts:
            continue
        cmd = parts[0].lower()
        if cmd == "rpm" and len(parts) == 2:
            try:
                q.put(("rpm", float(parts[1])))
            except ValueError:
                print("rpm vyzaduje cislo")
        elif cmd == "stop":
            q.put(("rpm", 0.0))
        elif cmd in ("quit", "exit", "q"):
            stop_event.set()
            return
        else:
            print("prikazy: rpm <cislo> | stop | quit")


def run(cfg, motor, sock, stop_event, commands=None, quiet=False) -> dict:
    sc = cfg.sender
    peer = (cfg.network.peer_ip, int(cfg.network.port))
    period = 1.0 / float(sc.rate_hz)
    loop = PeriodicLoop(period, float(sc.spin_us) / 1e6)
    unw = Unwrapper()
    log = []
    rpm_set = 0.0
    ramp = RampLimiter(sc.ramp_rpm_s)
    mode = str(sc.mode)
    if mode not in ("library", "voltage_pi"):
        raise ValueError(f"neznamy sender.mode: {mode}")
    sp = cfg.speed_pi
    pi = None
    cog = None
    if mode == "voltage_pi":
        pi = SpeedPI(sp.kp_v_per_rpm, sp.ki_v_per_rpm_s, sp.kff_v_per_rpm, sp.kfc_v, sp.fc_w0_rpm,
                     sp.voltage_limit_v, sp.slew_v_s, sp.i_limit_v, sp.i_band_rpm)
        if sp.cogging_table:
            cog = cogging.load(sp.cogging_table, 1.0, 0.5 * float(sp.voltage_limit_v))
    guard = safety.make_speed_guard(cfg.safety)
    overspeed = float(sc.max_rpm) * float(cfg.safety.overspeed_factor)
    out = 0.0
    fault = ""
    seq = 0
    t0 = time.monotonic()
    last_print = t0
    motor.open()
    try:
        initial = float(sc.initial_rpm)
        if initial:
            rpm_set = _clamp_rpm(initial, sc, quiet)
            ramp.set_target(rpm_set)
        while not stop_event.is_set():
            loop.wait()
            while commands is not None and not commands.empty():
                kind, val = commands.get()
                if kind == "rpm":
                    rpm_set = _clamp_rpm(val, sc, quiet)
                    ramp.set_target(rpm_set)
            if pi is None and ramp.value != ramp.target:
                motor.set_speed_rpm(ramp.update(period))
            ms = motor.read()
            theta = unw.update(ms.theta_deg)
            rpm = guard.update(time.monotonic(), ms.speed_rpm, theta)
            if abs(rpm) > overspeed:
                fault = f"prekrocena rychlost {rpm:.0f} rpm > {overspeed:.0f} rpm"
                if not quiet:
                    print(f"[sender] FAULT: {fault}", flush=True)
                break                                   # finally: motor.stop() a STOP pakety receiveru
            if pi is not None:
                out = pi.update(ramp.update(period), rpm, period, cog(ms.theta_deg) if cog else 0.0)
                motor.set_voltage_v(out)
            pkt = protocol.Packet(seq, time.time_ns(), theta, rpm,
                                  protocol.FLAG_VALID)
            sock.sendto(protocol.pack(pkt), peer)
            seq += 1
            if sc.log_path:
                log.append((time.monotonic() - t0, pkt.seq, rpm_set, ramp.value, theta, ms.speed_rpm, out))
            now = time.monotonic()
            if not quiet and now - last_print >= 1.0:
                last_print = now
                print(f"[sender] seq={seq} zadane={rpm_set:.0f} rpm "
                      f"nameranych={rpm:.0f} rpm uhol={theta:.1f} deg"
                      + (f" u={out:+.2f} V" if pi is not None else ""), flush=True)
    finally:
        try:
            motor.stop()
        finally:
            for _ in range(5):          # povedz receiveru, ze koncime
                stop_pkt = protocol.Packet(seq, time.time_ns(), 0.0, 0.0, protocol.FLAG_STOP)
                try:
                    sock.sendto(protocol.pack(stop_pkt), peer)
                except OSError:
                    break
                seq += 1
                time.sleep(0.005)
            motor.close()
        if sc.log_path and log:
            with open(sc.log_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["t_s", "seq", "rpm_set", "rpm_ref", "theta_deg", "speed_rpm", "u"])
                w.writerows(log)
    stats = loop.stats()
    stats["sent"] = seq
    stats["fault"] = fault
    stats["speed_glitches"] = guard.glitches
    return stats


def _clamp_rpm(rpm, sc, quiet):
    limit = float(sc.max_rpm)
    if abs(rpm) > limit:
        rpm = limit if rpm > 0 else -limit
        if not quiet:
            print(f"[sender] rychlost obmedzena na {rpm:.0f} rpm (sender.max_rpm)")
    if 0 < abs(rpm) < float(sc.min_rpm_warn) and not quiet:
        print(f"[sender] pozor: pod {sc.min_rpm_warn:.0f} rpm sa motor nemusi rozbehnut")
    return rpm
