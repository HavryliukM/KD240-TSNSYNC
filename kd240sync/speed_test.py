"""Test rychlostneho servopohonu na jednom motore: skoky ziadanej rychlosti, zaznam do RAM, CSV po skonceni.

Dva rezimy:
  voltage - vlastny PI regulator rychlosti (controller.SpeedPI) s vystupom napatie Vq, beh na control_hz.
  library - rezim Speed kniznice AMD (regulator v kniznici; 4. 11. 2026 trvala odchylka 50 az 80 %, zmeny
            v tikoch po 0,5 s, kazdu sekundu volanie zasekne ~50 ms). Ponechane na porovnanie.
V kazdej vzorke sa zapise ziadana a skutocna rychlost (surova aj vyhladena pre regulator), poloha, vystup
regulatora u a volitelne prud i_q/i_d z kniznice (citanie trva ~0,5 ms, preto predvolene vypnute).
"""
import csv
from array import array
from collections import deque
from time import perf_counter_ns

from . import cogging, safety
from .angle import Unwrapper
from .controller import SpeedPI
from .position_test import parse_steps
from .timing import PeriodicLoop

COLUMNS = ("t_s", "ref_rpm", "speed_rpm", "speed_f", "u", "theta_deg", "raw_deg", "i_q", "i_d", "read_us",
           "dbg_us")

__all__ = ["COLUMNS", "make_speed_pi", "parse_steps", "run", "write_csv"]


def make_speed_pi(sp):
    return SpeedPI(sp.kp_v_per_rpm, sp.ki_v_per_rpm_s, sp.kff_v_per_rpm, sp.kfc_v, sp.fc_w0_rpm,
                   sp.voltage_limit_v, sp.slew_v_s, sp.i_limit_v)


def run(cfg, motor, steps, sample_hz=2000.0, settle_s=0.5, max_rpm=1500.0, dbg_div=0, mode="voltage",
        control_hz=1000.0, log=print, loop=None):
    """steps = [(ziadana rychlost [ot/min], trvanie [s])]. Pred prvym usekom settle_s na 0 ot/min.

    dbg_div = citanie prudu z kniznice kazdu N-tu vzorku, 0 = vypnute. Vrati dict: data, fault, stats.
    """
    if mode not in ("voltage", "library"):
        raise ValueError(f"neznamy rezim {mode}")
    dt_s = 1.0 / float(sample_hz)
    div = max(1, round(float(sample_hz) / float(control_hz)))
    dt_c = div * dt_s
    sp = cfg.speed_pi
    pi = make_speed_pi(sp) if mode == "voltage" else None
    cog = (cogging.load(sp.cogging_table, 1.0, 0.5 * float(sp.voltage_limit_v))
           if mode == "voltage" and sp.cogging_table else None)
    filt = deque(maxlen=max(1, round(float(sp.speed_filter_s) * float(sample_hz))))
    segs = [(0.0, float(settle_s))] + [(float(r), float(h)) for r, h in steps]
    total = sum(h for _, h in segs)
    n_max = int((total + 1.0) * float(sample_hz)) + 16
    cols = [array("d", bytes(8 * n_max)) for _ in COLUMNS]
    t_c, ref_c, sp_c, spf_c, u_c, th_c, raw_c, iq_c, id_c, rd_c, db_c = cols
    guard = safety.make_speed_guard(cfg.safety)
    dbg = getattr(motor, "debug_read", None) if dbg_div else None
    unw = Unwrapper()
    fault = ""
    n = 0
    t_first = None
    theta0 = unw.update(motor.read().theta_deg)
    if loop is None:
        loop = PeriodicLoop(dt_s)
    seg_i, seg_t = 0, 0.0
    target = segs[0][0]
    out = 0.0
    if mode == "library":
        motor.set_speed_rpm(target)
    last = {"i_q": float("nan"), "i_d": float("nan")}
    try:
        while n < n_max:
            now = loop.wait()
            if t_first is None:
                t_first = now
            t = (now - t_first) / 1e9
            if t - seg_t >= segs[seg_i][1]:
                seg_i += 1
                if seg_i >= len(segs):
                    break
                seg_t = t
                target = segs[seg_i][0]
                if mode == "library":
                    motor.set_speed_rpm(target)
            r0 = perf_counter_ns()
            ms = motor.read()
            r1 = perf_counter_ns()
            if dbg and n % int(dbg_div) == 0:
                last.update(dbg())
            r2 = perf_counter_ns()
            theta = unw.update(ms.theta_deg) - theta0
            rpm = guard.update(now / 1e9, ms.speed_rpm, theta)
            filt.append(rpm)
            rpm_f = sum(filt) / len(filt)
            if abs(rpm) > max_rpm:
                fault = f"prekrocena rychlost {rpm:.0f} ot/min > {max_rpm:.0f} ot/min"
            elif pi is not None and n % div == 0:
                out = pi.update(target, rpm_f, dt_c, cog(ms.theta_deg) if cog else 0.0)
                motor.set_voltage_v(out)
            t_c[n] = t
            ref_c[n] = target
            sp_c[n] = ms.speed_rpm
            spf_c[n] = rpm_f
            u_c[n] = out if pi is not None else float("nan")
            th_c[n] = theta
            raw_c[n] = ms.theta_deg
            iq_c[n] = last["i_q"]
            id_c[n] = last["i_d"]
            rd_c[n] = (r1 - r0) / 1e3
            db_c[n] = (r2 - r1) / 1e3
            n += 1
            if fault:
                break
    finally:
        motor.stop()
    if fault:
        log(f"[speed_test] FAULT: {fault}")
    data = {name: col[:n] for name, col in zip(COLUMNS, cols)}
    stats = loop.stats()
    stats.update({"samples": n, "fault": fault, "speed_glitches": guard.glitches})
    if n:
        rd = sorted(data["read_us"])
        db = sorted(data["dbg_us"])
        stats["read_us_mean"] = sum(rd) / n
        stats["read_us_max"] = rd[-1]
        stats["dbg_us_mean"] = sum(db) / n
        stats["dbg_us_max"] = db[-1]
        stats["period_ms_mean"] = (data["t_s"][-1] - data["t_s"][0]) / max(1, n - 1) * 1e3
    return {"data": data, "fault": fault, "stats": stats}


def write_csv(path, data):
    n = len(data[COLUMNS[0]])
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for i in range(n):
            w.writerow([f"{data['t_s'][i]:.6f}"] + [f"{data[c][i]:.4f}" for c in COLUMNS[1:]])
