"""Test polohoveho servopohonu na jednom motore: skoky/rampy polohy, rychly zaznam do RAM (bez siete).

Slucka bezi s periodou 1/sample_hz (predvolene 1 kHz) a v kazdej vzorke zapise cas, ziadanu a skutocnu polohu,
rychlost, vystup regulatora a trvanie motor.read(). Regulator sa vola kazdu sample_hz/control_hz-tu vzorku
(predvolene 200 Hz ako v receiveri). Zapis na disk az po skonceni, aby I/O nerobilo jitter.
"""
import csv
import math
from array import array
from time import perf_counter_ns

from . import safety
from .angle import Unwrapper
from .config import Cfg
from .receiver import make_controller
from .timing import PeriodicLoop

COLUMNS = ("t_s", "ref_deg", "theta_deg", "speed_rpm", "err_deg", "u", "read_us")


def parse_steps(text):
    """'90:2,180:2,0:2' -> [(90.0, 2.0), (180.0, 2.0), (0.0, 2.0)] (cielova poloha [deg] od startu : drzanie [s])."""
    steps = []
    for item in text.split(","):
        target, _, hold = item.strip().partition(":")
        steps.append((float(target), float(hold) if hold else 2.0))
    if not steps:
        raise ValueError("prazdny profil")
    return steps


class Reference:
    """Ziadana poloha: skok (ramp_dps = 0) alebo rampa danou rychlostou. Drzanie sa pocita od zmeny ciela."""

    def __init__(self, steps, settle_s, ramp_dps):
        self.segments = [(0.0, float(settle_s))] + list(steps)
        self.ramp = float(ramp_dps)
        self.i = 0
        self.t_seg = 0.0
        self.value = 0.0
        self.w_dps = 0.0
        self.done = False

    def update(self, dt):
        target, hold = self.segments[self.i]
        self.t_seg += dt
        if self.ramp > 0.0 and self.value != target:
            step = self.ramp * dt
            moved = max(-step, min(step, target - self.value))
            self.value += moved
            self.w_dps = moved / dt
        else:
            self.value = target
            self.w_dps = 0.0
        if self.t_seg >= hold:
            if self.i + 1 >= len(self.segments):
                self.done = True
            else:
                self.i += 1
                self.t_seg = 0.0
        return self.value

    @property
    def total_s(self):
        return sum(h for _, h in self.segments)


def run(cfg, motor, steps, sample_hz=1000.0, control_hz=None, ramp_dps=0.0, settle_s=0.5,
        max_error_deg=None, max_rpm=600.0, spin_us=0.0, log=print):
    """Vykona profil na uz otvorenom motore. Vrati dict: data (stlpce), fault, stats."""
    rc = cfg.receiver
    if rc.mode not in ("voltage_pd", "torque_pd"):
        raise ValueError(f"receiver.mode {rc.mode} nie je polohovy PD regulator")
    voltage_mode = rc.mode == "voltage_pd"
    control_hz = float(control_hz or rc.rate_hz)
    div = max(1, round(float(sample_hz) / control_hz))
    dt_s = 1.0 / float(sample_hz)
    dt_c = div * dt_s

    ref = Reference(steps, settle_s, ramp_dps)
    span = max(abs(b - a) for a, b in zip([0.0] + [t for t, _ in steps], [t for t, _ in steps]))
    if max_error_deg is None:
        max_error_deg = min(180.0, span + 30.0)
    # skok polohy je zamerny: spike a dlhe nasytenie (limit 0 = kontrola vypnuta) by dali zbytocny FAULT
    sc = Cfg(dict(cfg.safety))
    sc["spike_deg"] = 1e9
    ctrl = make_controller(rc, cfg.safety)
    sup = safety.Supervisor(sc, dt_c, max_error_deg, max_rpm)

    n_max = int((ref.total_s + 1.0) * float(sample_hz)) + 16
    cols = [array("d", bytes(8 * n_max)) for _ in COLUMNS]
    t_c, ref_c, th_c, sp_c, err_c, u_c, rd_c = cols

    unw = Unwrapper()
    fault = ""
    out = 0.0
    n = 0
    t_first = None

    theta0 = unw.update(motor.read().theta_deg)
    loop = PeriodicLoop(dt_s, float(spin_us) / 1e6)
    try:
        while not ref.done and n < n_max:
            now = loop.wait()
            if t_first is None:
                t_first = now
            r0 = perf_counter_ns()
            ms = motor.read()
            read_us = (perf_counter_ns() - r0) / 1e3
            theta = unw.update(ms.theta_deg) - theta0
            r = ref.update(dt_s)
            err = r - theta
            if n % div == 0:
                out = ctrl.update(err, ref.w_dps - ms.speed_rpm * 6.0, dt_c, ref.w_dps)
                reason = sup.check(now / 1e9, err, out, 0.0, ms.speed_rpm)
                if reason:
                    fault = reason
                    break
                if voltage_mode:
                    motor.set_voltage_v(out)
                else:
                    motor.set_torque_a(out)
            t_c[n] = (now - t_first) / 1e9
            ref_c[n] = r
            th_c[n] = theta
            sp_c[n] = ms.speed_rpm
            err_c[n] = err
            u_c[n] = out
            rd_c[n] = read_us
            n += 1
    finally:
        motor.stop()
    if fault:
        log(f"[position_test] FAULT: {fault}")

    data = {name: col[:n] for name, col in zip(COLUMNS, cols)}
    stats = loop.stats()
    stats["samples"] = n
    stats["fault"] = fault
    if n:
        rd = sorted(data["read_us"])
        stats["read_us_mean"] = sum(rd) / n
        stats["read_us_p99"] = rd[min(n - 1, int(0.99 * n))]
        stats["read_us_max"] = rd[-1]
        stats["period_ms_mean"] = (data["t_s"][-1] - data["t_s"][0]) / max(1, n - 1) * 1e3
        stats["err_rms_deg"] = math.sqrt(sum(e * e for e in data["err_deg"]) / n)
    return {"data": data, "fault": fault, "stats": stats}


def write_csv(path, data):
    n = len(data[COLUMNS[0]])
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for i in range(n):
            w.writerow([f"{data['t_s'][i]:.6f}"] + [f"{data[c][i]:.4f}" for c in COLUMNS[1:]])
