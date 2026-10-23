"""Doska 2: prijima uhol z dosky 1 a regulatorom polohy ho sleduje vlastnym motorom."""
import csv
import math
import socket
import threading
import time

from . import protocol
from .angle import Unwrapper
from . import safety
from .controller import SpeedP, TorquePD
from .timing import PeriodicLoop

WAIT, RUN, FAULT = "WAIT", "RUN", "FAULT"


class RxThread(threading.Thread):
    """Blokujuco prijima pakety a hned po prijati ulozi cas (monotonic i realtime)."""

    def __init__(self, sock, stop_event):
        super().__init__(daemon=True)
        self.sock, self.stop_event = sock, stop_event
        self.lock = threading.Lock()
        self.latest = None          # (Packet, t_rx_mono_ns)
        self.rx = self.lost = self.reordered = self.bad = 0
        self.last_seq = -1
        self.lat_n = 0
        self.lat_sum = 0.0
        self.lat_min = math.inf
        self.lat_max = -math.inf
        self.last_lat_ms = float("nan")

    def run(self):
        while not self.stop_event.is_set():
            try:
                data, _ = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            t_mono = time.monotonic_ns()
            t_real = time.time_ns()
            try:
                p = protocol.unpack(data)
            except protocol.ProtocolError:
                with self.lock:
                    self.bad += 1
                continue
            with self.lock:
                if p.seq <= self.last_seq:
                    self.reordered += 1
                    continue
                if self.last_seq >= 0 and p.seq > self.last_seq + 1:
                    self.lost += p.seq - self.last_seq - 1
                self.last_seq = p.seq
                self.rx += 1
                self.latest = (p, t_mono)
                lat = (t_real - p.t_tx_ns) / 1e6      # ms; ma zmysel len pri synchronizovanych hodinach
                self.last_lat_ms = lat
                self.lat_n += 1
                self.lat_sum += lat
                self.lat_min = min(self.lat_min, lat)
                self.lat_max = max(self.lat_max, lat)

    def snapshot(self):
        with self.lock:
            return self.latest, self.last_lat_ms


def make_controller(rc, sc=None):
    """sc = cfg.safety: ak je zadane, zosilnenia sa obmedzia na stabilny rozsah."""
    if rc.mode == "torque_pd":
        t = rc.torque_pd
        kp, kd, ki = t.kp_a_per_deg, t.kd_a_per_dps, t.ki_a_per_deg_s
        limit, slew = t.torque_limit_a, t.slew_a_s
        if sc is not None:
            v, warns = safety.clamp_gains(kp, kd, ki, limit, slew, rc.max_error_deg,
                                          1.0 / float(rc.rate_hz), sc)
            kp, kd, ki, limit, slew = v["kp"], v["kd"], v["ki"], v["torque_limit_a"], v["slew_a_s"]
            for w in warns:
                print(f"[safety] {w}", flush=True)
        return TorquePD(kp, kd, ki, limit, slew, t.i_limit_a, t.deadband_deg)
    if rc.mode == "speed_p":
        s = rc.speed_p
        return SpeedP(s.kp_rpm_per_deg, s.max_rpm)
    raise ValueError(f"neznamy receiver.mode: {rc.mode}")


def run(cfg, motor, sock, stop_event, quiet=False) -> dict:
    rc = cfg.receiver
    period = 1.0 / float(rc.rate_hz)
    dt = period
    timeout_ns = int(float(rc.timeout_ms) * 1e6)
    sign = 1.0 if int(rc.direction) >= 0 else -1.0
    ratio = float(rc.ratio)
    max_err = float(rc.max_error_deg)
    ctrl = make_controller(rc, cfg.safety)
    sup = safety.Supervisor(cfg.safety, period, max_err,
                            float(cfg.sender.max_rpm) * float(cfg.safety.overspeed_factor))
    torque_mode = rc.mode == "torque_pd"
    unw = Unwrapper()
    loop = PeriodicLoop(period, float(rc.spin_us) / 1e6)
    rx = RxThread(sock, stop_event)
    log = []
    state = WAIT
    off_remote = off_local = 0.0
    err_sq = 0.0
    err_n = 0
    err_max = 0.0
    fault_reason = ""
    t0 = time.monotonic()
    last_print = t0
    motor.open()
    rx.start()
    try:
        while not stop_event.is_set():
            now = loop.wait()
            snap, lat_ms = rx.snapshot()
            ms = motor.read()
            local = unw.update(ms.theta_deg)
            if state == FAULT:
                continue
            fresh = False
            pkt = None
            age_ns = 0
            if snap is not None:
                pkt, t_rx = snap
                age_ns = now - t_rx
                fresh = (not pkt.stop) and age_ns <= timeout_ns
            if not fresh:
                if state == RUN:
                    motor.stop()
                    ctrl.reset()
                    state = WAIT
                    if not quiet:
                        print("[receiver] pakety nepridu / STOP -> motor uvolneny", flush=True)
                continue
            age_s = age_ns / 1e9
            remote = pkt.theta_deg + pkt.omega_rpm * 6.0 * age_s   # extrapolacia o vek paketu
            if state == WAIT:
                off_remote, off_local = remote, local                # zarovnanie bez skoku
                ctrl.reset()
                sup.reset()
                state = RUN
                if not quiet:
                    print("[receiver] RUN (zarovnane)", flush=True)
            ref = off_local + sign * ratio * (remote - off_remote)
            w_ref = sign * ratio * pkt.omega_rpm * 6.0
            err = ref - local
            if torque_mode:
                out = ctrl.update(err, w_ref - ms.speed_rpm * 6.0, dt)
            else:
                out = ctrl.update(err, w_ref, dt)
            reason = sup.check(now / 1e9, err, out, getattr(ctrl, "limit", 0.0), ms.speed_rpm)
            if reason:
                motor.stop()
                state = FAULT
                fault_reason = reason
                if not quiet:
                    print(f"[receiver] FAULT: {fault_reason}", flush=True)
                continue
            if torque_mode:
                motor.set_torque_a(out)
            else:
                motor.set_speed_rpm(out)
            err_sq += err * err
            err_n += 1
            err_max = max(err_max, abs(err))
            if rc.log_path:
                log.append((time.monotonic() - t0, state, pkt.seq, ref, local, err, out,
                            age_s * 1e3, lat_ms))
            tnow = time.monotonic()
            if not quiet and tnow - last_print >= float(rc.status_period_s):
                last_print = tnow
                print(f"[receiver] {state} seq={pkt.seq} chyba={err:+.2f} deg "
                      f"vystup={out:+.3f} vek={age_s*1e3:.1f} ms strat={rx.lost}", flush=True)
    finally:
        try:
            motor.stop()
        finally:
            motor.close()
        if rc.log_path and log:
            with open(rc.log_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["t_s", "state", "seq", "ref_deg", "local_deg", "err_deg",
                            "output", "age_ms", "lat_ms"])
                w.writerows(log)
    stats = loop.stats()
    stats.update({
        "state": state, "fault": fault_reason,
        "rx": rx.rx, "lost": rx.lost, "reordered": rx.reordered, "bad": rx.bad,
        "err_rms_deg": math.sqrt(err_sq / err_n) if err_n else float("nan"),
        "err_max_deg": err_max,
        "lat_mean_ms": rx.lat_sum / rx.lat_n if rx.lat_n else float("nan"),
        "lat_min_ms": rx.lat_min if rx.lat_n else float("nan"),
        "lat_max_ms": rx.lat_max if rx.lat_n else float("nan"),
    })
    return stats
