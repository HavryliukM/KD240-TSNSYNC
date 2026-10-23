#!/usr/bin/env python3
"""Web Dashboard Server pre KD240 TSN Synchronizaciu.

Poskytuje moderny webovy dashboard na monitorovanie a riadenie synchronizacie
dvoch motorov cez TSN alebo samostatne testovanie pohonov.

Funguje bez akychkolvek externych kniznic (len cisty Python standard library).

Pouzitie:
  # 1. Spustenie na PC v simulacii (synchronizacia 2 motorov cez localhost):
  python3 -m web.server --mode demo --port 8080

  # 2. Spustenie na Doske 1 (Sender / Master s realnym motorom):
  sudo python3 -m web.server --mode sender --backend foc_lib --port 8080

  # 3. Spustenie na Doske 2 (Receiver / Slave s realnym motorom):
  sudo python3 -m web.server --mode receiver --backend foc_lib --port 8080

  # 4. Spustenie na jednej doske len na priame testovanie motora:
  sudo python3 -m web.server --mode single --backend foc_lib --port 8080
"""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import collections
import copy
import datetime
import json
import logging
import math
import os
import queue
import random
import socket
import sys
import threading
import time

# Zabezpecenie importov z korenoveho adresara
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kd240sync import angle, config, controller, motor as motor_mod, net, protocol, receiver, safety, timing

MAX_TORQUE_A = 2.5
TUNE_LIMITS = {
    "kp": (0.0, 1.0),
    "kd": (0.0, 0.1),
    "ki": (0.0, 0.1),
    "torque_limit_a": (0.0, MAX_TORQUE_A),
    "slew_a_s": (0.0, 5000.0),
    "max_error_deg": (1.0, 3600.0),
}
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
log = logging.getLogger("web_server")


RampLimiter = controller.RampLimiter


def _finite(value, name):
    """Prevedie na konecne float, inak ValueError (None, text, NaN, inf)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} musi byt cislo") from None
    if not math.isfinite(v):
        raise ValueError(f"{name} musi byt konecne cislo")
    return v


class SystemManager:
    """Spravuje beh synchronizacie a poskytuje telemetriu pre webove rozhranie."""

    def __init__(self, mode="demo", backend="sim", cfg_path=None):
        self.mode = mode
        self.backend = backend
        self.cfg_path = cfg_path
        self.running = False
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.commands = queue.SimpleQueue()
        self.lock = threading.Lock()
        base_cfg = config.load(cfg_path)
        self.max_rpm = float(base_cfg.sender.max_rpm)
        self.max_torque_a = float(base_cfg.receiver.torque_pd.torque_limit_a)
        self.dt = 1.0 / float(base_cfg.receiver.rate_hz)
        self.safety_cfg = base_cfg.safety
        self.speed_p = base_cfg.receiver.mode == "speed_p"

        # Telemetria casovania paketov (Tx -> Rx)
        self.recent_packets = collections.deque(maxlen=25)
        self.latencies_us = collections.deque(maxlen=100)
        self.csv_history = collections.deque(maxlen=2000)
        self._last_logged_seq = -1
        self.jitter_us = 0.0
        self._prev_lat_us = None

        # Telemetricky stav
        self.status = {
            "mode": self.mode,
            "backend": self.backend,
            "state": "IDLE",
            "active": False,
            "motor1": {
                "rpm_set": 0.0,
                "speed_rpm": 0.0,
                "theta_deg": 0.0,
                "theta_mod": 0.0,
                "turns": 0.0,
            },
            "motor2": {
                "speed_rpm": 0.0,
                "theta_deg": 0.0,
                "theta_mod": 0.0,
                "turns": 0.0,
                "output_a": 0.0,
            },
            "sync": {
                "error_deg": 0.0,
                "ref_deg": 0.0,
                "local_deg": 0.0,
                "lat_ms": 0.0,
                "lat_us": 0.0,
                "avg_lat_us": 0.0,
                "jitter_us": 0.0,
                "lost_pkts": 0,
                "seq": 0,
                "rate_hz": 200,
            },
            "recent_packets": [],
            "tuning": {
                "kp": 0.022,
                "kd": 0.00045,
                "ki": 0.0004,
                "torque_limit_a": 1.5,
                "slew_a_s": 500.0,
                "max_error_deg": 60.0,
            },
            "fault": "",
            "tuning_warn": [],
            "ts": time.time(),
        }

    def start(self):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        with self.lock:
            self.status["active"] = True
            self.status["state"] = "RUN" if self.mode in ("demo", "sender", "single") else "WAIT"
        target = {"demo": self._run_demo, "sender": self._run_sender,
                  "receiver": self._run_receiver, "single": self._run_single}[self.mode]
        self.worker_thread = threading.Thread(target=self._guarded, args=(target,), daemon=True)
        self.worker_thread.start()

    def _guarded(self, target):
        """Chyba vo workeri (napr. chybajuca kniznica motora) sa zobrazi ako FAULT."""
        try:
            target()
        except Exception as err:
            log.exception("worker zlyhal")
            with self.lock:
                self.status["fault"] = f"Worker zlyhal: {err}"
                self.status["state"] = "FAULT"
                self.status["active"] = False
            self.running = False

    def stop(self):
        self.stop_event.set()
        self.running = False
        with self.lock:
            self.status["state"] = "IDLE"
            self.status["active"] = False

    def send_command(self, cmd_type, value):
        self.commands.put((cmd_type, value))

    def get_status(self):
        with self.lock:
            st = copy.deepcopy(self.status)
            st["ts"] = time.time()
            return st

    # --- Worker metody pre jednotlive rezimy ---

    def _run_single(self, default_rpm=0.0):
        """Ovladanie jedneho motora bez TSN siete."""
        cfg = config.load(self.cfg_path, overrides={"motor": {"backend": self.backend}})
        motor = motor_mod.create(cfg)
        motor.open()
        current_rpm = default_rpm
        unw = angle.Unwrapper()
        with self.lock:
            self.status["state"] = "RUN"
            self.status["active"] = True

        try:
            while not self.stop_event.is_set():
                while not self.commands.empty():
                    k, v = self.commands.get()
                    if k == "rpm":
                        current_rpm = float(v)
                        motor.set_speed_rpm(current_rpm)
                    elif k == "torque":
                        motor.set_torque_a(float(v))
                    elif k == "stop":
                        current_rpm = 0.0
                        motor.stop()
                    elif k == "clear_fault":
                        if hasattr(motor, "clear_faults"):
                            motor.clear_faults()
                        with self.lock:
                            self.status["fault"] = ""

                ms = motor.read()
                th = unw.update(ms.theta_deg)
                with self.lock:
                    self.status["motor1"]["rpm_set"] = current_rpm
                    self.status["motor1"]["speed_rpm"] = round(ms.speed_rpm, 1)
                    self.status["motor1"]["theta_deg"] = round(th, 2)
                    self.status["motor1"]["theta_mod"] = round(((th % 360.0) + 360.0) % 360.0, 1)
                    self.status["motor1"]["turns"] = round(th / 360.0, 2)
                time.sleep(0.01)
        finally:
            motor.stop()
            motor.close()

    def _run_demo(self):
        base_overrides = {
            "motor": {"backend": "sim"},
            "network": {"port": 0, "bind_ip": "127.0.0.1", "peer_ip": "127.0.0.1"}
        }
        cfg = config.load(self.cfg_path, overrides=base_overrides)
        rsock = net.make_receiver_socket(cfg, timeout_s=0.002)
        rsock.setblocking(False)
        port = rsock.getsockname()[1]
        cfg["network"]["port"] = port
        ssock = net.make_sender_socket(cfg)
        # Virtualny cas: kazdy cyklus posunie simulaciu presne o dt, takze vypadky planovaca
        # hostitelskeho PC (Windows) nevyrobia v demu falosnu regulacnu chybu.
        vnow = [0]
        vclock = lambda: vnow[0]
        m1 = motor_mod.SimMotor(**cfg.motor.sim, clock=vclock)
        m2 = motor_mod.SimMotor(**cfg.motor.sim, clock=vclock)
        m1.open()
        m2.open()

        unw1 = angle.Unwrapper()
        unw2 = angle.Unwrapper()
        rate_hz = float(cfg.sender.rate_hz)
        dt = 1.0 / rate_hz
        ctrl = receiver.make_controller(cfg.receiver, cfg.safety)
        loop = timing.PeriodicLoop(dt)
        timeout_ns = int(float(cfg.receiver.timeout_ms) * 1e6)

        # Model TSN linky pre demo (hodnoty z [sim_net] v konfiguracii)
        sn = cfg.sim_net
        rng = random.Random(1)
        net_delay_us, net_jitter_us = float(sn.delay_us), float(sn.jitter_us)
        net_spike_p, net_spike_us = float(sn.spike_prob), float(sn.spike_us)
        net_loss = float(sn.loss)
        pending = []
        last_pkt = None
        last_seq = -1
        lost = net_lost = 0
        new_pkt = False
        lat_us = lat_ms = 0.0
        last_err = 0.0

        rpm_set = 0.0
        ramp = RampLimiter(cfg.sender.ramp_rpm_s)
        seq = 0
        state = "RUN"
        off_remote = off_local = 0.0
        is_synced = False
        max_err = float(cfg.receiver.max_error_deg)
        sup = safety.Supervisor(cfg.safety, dt, max_err,
                                float(cfg.sender.max_rpm) * float(cfg.safety.overspeed_factor))

        with self.lock:
            self.status["state"] = "RUN"
            self.status["active"] = True
            self.status["sync"]["rate_hz"] = rate_hz
            # Uloz aktualne parametre regulatora do statusu
            self.status["tuning"] = {
                "kp": ctrl.kp, "kd": ctrl.kd, "ki": ctrl.ki,
                "torque_limit_a": ctrl.limit, "slew_a_s": ctrl.slew,
                "max_error_deg": max_err,
            }

        try:
            while not self.stop_event.is_set():
                loop.wait()
                vnow[0] += int(dt * 1e9)
                while not self.commands.empty():
                    k, v = self.commands.get()
                    if k == "rpm":
                        rpm_set = float(v)
                        if state != "FAULT":
                            ramp.set_target(rpm_set)
                    elif k == "stop":
                        rpm_set = 0.0
                        ramp.jump(0.0)
                        m1.stop()
                        m2.stop()
                        ctrl.reset()
                        is_synced = False
                        last_err = 0.0
                    elif k == "clear_fault":
                        # Zastavime oba motory na 0, vycistime socket buffer a resetujeme zarovnanie
                        rpm_set = 0.0
                        ramp.jump(0.0)
                        m1.stop()
                        m2.stop()
                        ctrl.reset()
                        is_synced = False
                        last_pkt = None
                        pending = []
                        last_err = 0.0
                        while True:
                            try:
                                rsock.recvfrom(2048)
                            except Exception:
                                break
                        state = "RUN"
                        with self.lock:
                            self.status["fault"] = ""
                            self.status["state"] = "RUN"
                            self.status["motor1"]["rpm_set"] = 0.0
                            self.status["sync"]["error_deg"] = 0.0
                    elif k == "tune":
                        max_err = self._apply_tuning(ctrl, v, max_err, dt, cfg.safety)
                        sup.max_err = max_err
                        with self.lock:
                            self.status["tuning"] = self._tuning_snapshot(ctrl, max_err)

                # 1. Krok Sender (Motor 1): ziadana rychlost sa meni len rampou
                if state != "FAULT" and ramp.value != ramp.target:
                    m1.set_speed_rpm(ramp.update(dt))
                st1 = m1.read()
                th1 = unw1.update(st1.theta_deg)
                pkt = protocol.Packet(seq, time.time_ns(), th1, st1.speed_rpm, protocol.FLAG_VALID)
                ssock.sendto(protocol.pack(pkt), ("127.0.0.1", port))
                seq += 1

                # 2. Simulovana TSN siet: paket sa dorucí po case delay +- jitter, ojedinele
                #    s dodatocnym oneskorenim (spike) alebo sa straci. Localhost je len transport.
                while True:
                    try:
                        data, _ = rsock.recvfrom(2048)
                        p = protocol.unpack(data)
                    except (BlockingIOError, socket.timeout):
                        break
                    except protocol.ProtocolError:
                        continue
                    except OSError:
                        break
                    if rng.random() < net_loss:
                        net_lost += 1
                        continue
                    delay_us = max(0.0, rng.gauss(net_delay_us, net_jitter_us))
                    if rng.random() < net_spike_p:
                        delay_us += net_spike_us
                    pending.append((vnow[0] + int(delay_us * 1e3), delay_us, p))
                now = vnow[0]
                due = [x for x in pending if x[0] <= now]
                if due:
                    pending = [x for x in pending if x[0] > now]
                    due.sort(key=lambda x: x[2].seq)
                    for t_due, d_us, p in due:
                        if p.seq > last_seq:
                            if last_seq >= 0 and p.seq > last_seq + 1:
                                lost += p.seq - last_seq - 1
                            last_seq = p.seq
                            last_pkt = (p, t_due, d_us)
                            new_pkt = True

                # 3. Krok Receiver (Motor 2)
                st2 = m2.read()
                local = unw2.update(st2.theta_deg)
                out = 0.0

                if state != "FAULT" and last_pkt is not None:
                    rx_pkt, t_rx_mono, delay_us = last_pkt
                    age_s = max(0, now - t_rx_mono) / 1e9
                    if age_s * 1e9 > timeout_ns:
                        # pakety neprichadzaju -> motor 2 uvolnit, po obnoveni sa znova zarovna
                        if is_synced:
                            m2.stop()
                            ctrl.reset()
                            is_synced = False
                        err = 0.0
                    else:
                        remote = rx_pkt.theta_deg + rx_pkt.omega_rpm * 6.0 * age_s
                        if not is_synced:
                            off_remote, off_local = remote, local
                            ctrl.reset()
                            sup.reset()
                            is_synced = True
                        ref = off_local + (remote - off_remote)
                        err = ref - local
                        w_ff = rx_pkt.omega_rpm * 6.0
                        out = ctrl.update(err, w_ff - st2.speed_rpm * 6.0, dt)
                        reason = sup.check(now / 1e9, err, out, ctrl.limit, st2.speed_rpm)
                        if new_pkt:
                            lat_us = delay_us
                            lat_ms = lat_us / 1000.0
                            self.latencies_us.append(lat_us)
                            self._note_jitter(lat_us)
                            entry = self._packet_entry(rx_pkt, time.time_ns(), lat_us, lat_ms,
                                                       th1, local, err, st1.speed_rpm, max_err)
                            self.recent_packets.append(entry)
                            self.csv_history.append(entry)
                        if reason:
                            # FAULT: zastavime OBA motory okamzite
                            m1.stop()
                            m2.stop()
                            rpm_set = 0.0
                            ramp.jump(0.0)
                            out = 0.0
                            state = "FAULT"
                            with self.lock:
                                self.status["fault"] = f"Poistka: {reason}"
                                self.status["state"] = "FAULT"
                                self.status["motor1"]["rpm_set"] = 0.0
                        else:
                            m2.set_torque_a(out)
                        last_err = err
                else:
                    err = 0.0 if state == "FAULT" else last_err
                new_pkt = False

                avg_lat_us = sum(self.latencies_us) / len(self.latencies_us) if self.latencies_us else 0.0
                jitter_us = self.jitter_us

                with self.lock:
                    self.status["state"] = state
                    self.status["motor1"]["rpm_set"] = rpm_set
                    self.status["motor1"]["speed_rpm"] = round(st1.speed_rpm, 1)
                    self.status["motor1"]["theta_deg"] = round(th1, 2)
                    self.status["motor1"]["theta_mod"] = round(((th1 % 360.0) + 360.0) % 360.0, 1)
                    self.status["motor1"]["turns"] = round(th1 / 360.0, 2)
                    self.status["motor2"]["speed_rpm"] = round(st2.speed_rpm, 1)
                    self.status["motor2"]["theta_deg"] = round(local, 2)
                    self.status["motor2"]["theta_mod"] = round(((local % 360.0) + 360.0) % 360.0, 1)
                    self.status["motor2"]["turns"] = round(local / 360.0, 2)
                    self.status["motor2"]["output_a"] = round(out, 3)
                    self.status["sync"]["error_deg"] = round(err, 2)
                    self.status["sync"]["seq"] = seq
                    self.status["sync"]["lost_pkts"] = lost + net_lost
                    self.status["sync"]["loop"] = loop.stats()
                    self.status["sync"]["lat_ms"] = round(lat_ms, 3)
                    self.status["sync"]["lat_us"] = round(lat_us, 1)
                    self.status["sync"]["avg_lat_us"] = round(avg_lat_us, 1)
                    self.status["sync"]["jitter_us"] = round(jitter_us, 1)
                    self.status["recent_packets"] = list(self.recent_packets)
        finally:
            m1.stop()
            m2.stop()
            m1.close()
            m2.close()
            ssock.close()
            rsock.close()

    def _run_sender(self):
        """Rezim Sender pre Dosku 1."""
        cfg = config.load(self.cfg_path or "config/board1.toml", overrides={"motor": {"backend": self.backend}})
        motor = motor_mod.create(cfg)
        sock = net.make_sender_socket(cfg)
        peer = (cfg.network.peer_ip, int(cfg.network.port))
        period = 1.0 / float(cfg.sender.rate_hz)
        loop = timing.PeriodicLoop(period)
        unw = angle.Unwrapper()
        rpm_set = min(abs(float(cfg.sender.initial_rpm)), self.max_rpm) * (1 if float(cfg.sender.initial_rpm) >= 0 else -1)
        ramp = RampLimiter(cfg.sender.ramp_rpm_s)
        ramp.set_target(rpm_set)

        motor.open()
        seq = 0
        with self.lock:
            self.status["state"] = "RUN"
            self.status["active"] = True

        try:
            while not self.stop_event.is_set():
                loop.wait()
                while not self.commands.empty():
                    k, v = self.commands.get()
                    if k == "rpm":
                        rpm_set = float(v)
                        ramp.set_target(rpm_set)
                    elif k == "stop":
                        rpm_set = 0.0
                        ramp.jump(0.0)
                        motor.stop()
                if ramp.value != ramp.target:
                    motor.set_speed_rpm(ramp.update(period))

                ms = motor.read()
                th = unw.update(ms.theta_deg)
                pkt = protocol.Packet(seq, time.time_ns(), th, ms.speed_rpm, protocol.FLAG_VALID)
                sock.sendto(protocol.pack(pkt), peer)
                seq += 1

                with self.lock:
                    self.status["motor1"]["rpm_set"] = rpm_set
                    self.status["motor1"]["speed_rpm"] = round(ms.speed_rpm, 1)
                    self.status["motor1"]["theta_deg"] = round(th, 2)
                    self.status["motor1"]["theta_mod"] = round(((th % 360.0) + 360.0) % 360.0, 1)
                    self.status["motor1"]["turns"] = round(th / 360.0, 2)
                    self.status["sync"]["seq"] = seq
        finally:
            motor.stop()
            for _ in range(5):          # povedz receiveru, ze koncime
                try:
                    sock.sendto(protocol.pack(protocol.Packet(
                        seq, time.time_ns(), 0.0, 0.0, protocol.FLAG_STOP)), peer)
                except OSError:
                    break
                seq += 1
                time.sleep(0.005)
            motor.close()
            sock.close()

    def _run_receiver(self):
        """Rezim Receiver pre Dosku 2."""
        cfg = config.load(self.cfg_path or "config/board2.toml", overrides={"motor": {"backend": self.backend}})
        motor = motor_mod.create(cfg)
        sock = net.make_receiver_socket(cfg)
        sock.setblocking(False)
        motor.open()

        rc = cfg.receiver
        rate_hz = float(rc.rate_hz)
        dt = 1.0 / rate_hz
        timeout_ns = int(float(rc.timeout_ms) * 1e6)
        sign = 1.0 if int(rc.direction) >= 0 else -1.0
        ratio = float(rc.ratio)
        max_err = float(rc.max_error_deg)
        ctrl = receiver.make_controller(rc, cfg.safety)
        sup = safety.Supervisor(cfg.safety, dt, max_err,
                                float(cfg.sender.max_rpm) * float(cfg.safety.overspeed_factor))
        torque_mode = rc.mode == "torque_pd"
        unw = angle.Unwrapper()
        loop = timing.PeriodicLoop(dt)

        state = "WAIT"
        off_remote = off_local = 0.0
        last_pkt = None          # (Packet, t_rx_wall_ns, t_rx_mono_ns)
        last_seq = -1
        lost = 0
        with self.lock:
            self.status["state"] = state
            self.status["active"] = True
            self.status["sync"]["rate_hz"] = rate_hz
            self.status["tuning"] = self._tuning_snapshot(ctrl, max_err)

        try:
            while not self.stop_event.is_set():
                now = loop.wait()
                while not self.commands.empty():
                    k, v = self.commands.get()
                    if k == "stop":
                        motor.stop()
                        ctrl.reset()
                        last_pkt = None
                        if state == "RUN":
                            state = "WAIT"
                    elif k == "clear_fault":
                        motor.stop()
                        ctrl.reset()
                        last_pkt = None
                        state = "WAIT"
                        while True:
                            try:
                                sock.recvfrom(2048)
                            except Exception:
                                break
                        with self.lock:
                            self.status["fault"] = ""
                            self.status["state"] = "WAIT"
                            self.status["sync"]["error_deg"] = 0.0
                    elif k == "tune":
                        max_err = self._apply_tuning(ctrl, v, max_err, dt, cfg.safety)
                        sup.max_err = max_err
                        with self.lock:
                            self.status["tuning"] = self._tuning_snapshot(ctrl, max_err)

                # Prijmi vsetky cakajuce pakety; last_pkt drzi najnovsi aj medzi cyklami
                while True:
                    try:
                        data, _ = sock.recvfrom(2048)
                        t_rx_wall = time.time_ns()
                        t_rx_mono = time.monotonic_ns()
                        p = protocol.unpack(data)
                    except (BlockingIOError, socket.timeout):
                        break
                    except protocol.ProtocolError:
                        continue
                    except OSError:
                        break
                    if p.seq <= last_seq and not p.stop:
                        continue
                    if last_seq >= 0 and p.seq > last_seq + 1:
                        lost += p.seq - last_seq - 1
                    last_seq = max(last_seq, p.seq)
                    last_pkt = (p, t_rx_wall, t_rx_mono)

                ms = motor.read()
                local = unw.update(ms.theta_deg)
                err = 0.0
                out = 0.0
                lat_us = 0.0
                lat_ms = 0.0

                fresh = (last_pkt is not None and not last_pkt[0].stop
                         and now - last_pkt[2] <= timeout_ns)
                if state == "FAULT":
                    pass
                elif fresh:
                    pkt, t_rx_wall, t_rx_mono = last_pkt
                    age_s = (now - t_rx_mono) / 1e9     # vek paketu na tejto doske (monotonic)
                    remote = pkt.theta_deg + pkt.omega_rpm * 6.0 * age_s
                    if state == "WAIT":
                        off_remote, off_local = remote, local
                        ctrl.reset()
                        sup.reset()
                        state = "RUN"
                    ref = off_local + sign * ratio * (remote - off_remote)
                    w_ref = sign * ratio * pkt.omega_rpm * 6.0
                    err = ref - local

                    # Jednosmerna latencia (presna len pri PTP-synchronizovanych hodinach)
                    lat_ns = max(0, t_rx_wall - pkt.t_tx_ns)
                    lat_us = lat_ns / 1000.0
                    lat_ms = lat_ns / 1_000_000.0
                    if pkt.seq != self._last_logged_seq:
                        self._last_logged_seq = pkt.seq
                        self.latencies_us.append(lat_us)
                        self._note_jitter(lat_us)
                        entry = self._packet_entry(pkt, t_rx_wall, lat_us, lat_ms, pkt.theta_deg,
                                                   local, err, ms.speed_rpm, max_err)
                        self.recent_packets.append(entry)
                        self.csv_history.append(entry)

                    if torque_mode:
                        out = ctrl.update(err, w_ref - ms.speed_rpm * 6.0, dt)
                    else:
                        out = ctrl.update(err, w_ref, dt)
                    reason = sup.check(now / 1e9, err, out, getattr(ctrl, "limit", 0.0), ms.speed_rpm)
                    if reason:
                        motor.stop()
                        out = 0.0
                        state = "FAULT"
                        with self.lock:
                            self.status["fault"] = f"Poistka: {reason}"
                    elif torque_mode:
                        motor.set_torque_a(out)
                    else:
                        motor.set_speed_rpm(out)
                elif state == "RUN":
                    # Pakety neprichadzaju (alebo STOP) -> motor uvolnit
                    motor.stop()
                    ctrl.reset()
                    state = "WAIT"

                avg_lat_us = sum(self.latencies_us) / len(self.latencies_us) if self.latencies_us else 0.0
                jitter_us = self.jitter_us

                with self.lock:
                    self.status["state"] = state
                    self.status["motor2"]["speed_rpm"] = round(ms.speed_rpm, 1)
                    self.status["motor2"]["theta_deg"] = round(local, 2)
                    self.status["motor2"]["theta_mod"] = round(((local % 360.0) + 360.0) % 360.0, 1)
                    self.status["motor2"]["turns"] = round(local / 360.0, 2)
                    self.status["motor2"]["output_a"] = round(out, 3)
                    self.status["sync"]["error_deg"] = round(err, 2)
                    self.status["sync"]["seq"] = max(last_seq, 0)
                    self.status["sync"]["lost_pkts"] = lost
                    self.status["sync"]["loop"] = loop.stats()
                    self.status["sync"]["lat_ms"] = round(lat_ms, 3)
                    self.status["sync"]["lat_us"] = round(lat_us, 1)
                    self.status["sync"]["avg_lat_us"] = round(avg_lat_us, 1)
                    self.status["sync"]["jitter_us"] = round(jitter_us, 1)
                    self.status["recent_packets"] = list(self.recent_packets)
        finally:
            motor.stop()
            motor.close()
            sock.close()

    # --- Pomocne metody ---

    @staticmethod
    def _tuning_snapshot(ctrl, max_err):
        return {
            "kp": getattr(ctrl, "kp", 0.0), "kd": getattr(ctrl, "kd", 0.0),
            "ki": getattr(ctrl, "ki", 0.0), "torque_limit_a": getattr(ctrl, "limit", 0.0),
            "slew_a_s": getattr(ctrl, "slew", 0.0), "max_error_deg": max_err,
        }

    def request_tuning(self, params):
        """Vola HTTP vlakno: obmedzi parametre na stabilny rozsah (safety.clamp_gains, moze trvat
        desiatky ms, preto nie v riadiacej slucke) a posle ich workeru."""
        with self.lock:
            cur = dict(self.status["tuning"])
        cur.update(params)
        if self.speed_p:                    # jine jednotky (rpm/deg): overenie stability sa nepouzije
            self.send_command("tune", cur)
            return cur, []
        v, warns = safety.clamp_gains(cur["kp"], cur["kd"], cur["ki"], cur["torque_limit_a"],
                                      cur["slew_a_s"], cur["max_error_deg"], self.dt, self.safety_cfg)
        with self.lock:
            self.status["tuning_warn"] = warns
        self.send_command("tune", v)
        return v, warns

    @staticmethod
    def _apply_tuning(ctrl, v, max_err, dt=None, sc=None):
        """Aplikuje uz obmedzene parametre na regulator a vrati aktualny max_err."""
        if hasattr(ctrl, "kd"):
            ctrl.kp, ctrl.kd, ctrl.ki = v["kp"], v["kd"], v["ki"]
            ctrl.limit, ctrl.slew = v["torque_limit_a"], v["slew_a_s"]
            ctrl.reset()                    # nove nastavenie nesmie zdedit stary integrator
        else:
            ctrl.kp = v["kp"]
        return v.get("max_error_deg", max_err)

    def _note_jitter(self, lat_us):
        """Jitter podla RFC 3550: vyhladena stredna absolutna zmena latencie (odolna voci spike)."""
        if self._prev_lat_us is not None:
            self.jitter_us += (abs(lat_us - self._prev_lat_us) - self.jitter_us) / 16.0
        self._prev_lat_us = lat_us

    @staticmethod
    def _packet_entry(pkt, t_rx_wall_ns, lat_us, lat_ms, theta_remote, local, err, speed_rpm, max_err):
        tx_dt = datetime.datetime.fromtimestamp(pkt.t_tx_ns / 1e9)
        rx_dt = datetime.datetime.fromtimestamp(t_rx_wall_ns / 1e9)
        return {
            "seq": pkt.seq,
            "tx_time": tx_dt.strftime("%H:%M:%S.%f")[:-3],
            "rx_time": rx_dt.strftime("%H:%M:%S.%f")[:-3],
            "lat_us": round(lat_us, 1),
            "lat_ms": round(lat_ms, 3),
            "theta_m1": round(((theta_remote % 360.0) + 360.0) % 360.0, 1),
            "theta_m2": round(((local % 360.0) + 360.0) % 360.0, 1),
            "err_deg": round(err, 2),
            "speed_rpm": round(speed_rpm, 1),
            "status": "OK" if abs(err) <= max_err else "WARN",
        }


class DashboardHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler pre API a staticke subory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    @property
    def manager(self):
        return getattr(self.server, "manager", None)

    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if self.path == "/api/status":
            st = self.manager.get_status() if self.manager else {}
            self._send_json(st)
        elif self.path == "/api/export_csv":
            self._send_csv()
        else:
            if self.path == "/" or not self.path:
                self.path = "/index.html"
            super().do_GET()

    def do_POST(self):
        if not self._origin_ok():
            self.send_error(403, "Zly Origin")
            return
        try:
            content_len = min(int(self.headers.get("Content-Length", 0)), 4096)
            post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"
            body = json.loads(post_data.decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("telo musi byt objekt")
        except (ValueError, UnicodeDecodeError):
            self._send_json({"ok": False, "error": "neplatny JSON"}, 400)
            return

        if not self.manager:
            self.send_error(503, "Manager nie je pripraveny")
            return

        mgr = self.manager
        try:
            if self.path == "/api/speed":
                rpm = _finite(body.get("rpm"), "rpm")
                if abs(rpm) > mgr.max_rpm:
                    raise ValueError(f"rpm mimo rozsahu +-{mgr.max_rpm:.0f}")
                mgr.send_command("rpm", rpm)
                self._send_json({"ok": True, "speed": rpm})
            elif self.path == "/api/torque":
                amps = _finite(body.get("amps"), "amps")
                if abs(amps) > MAX_TORQUE_A:
                    raise ValueError(f"prud mimo rozsahu +-{MAX_TORQUE_A} A")
                mgr.send_command("torque", amps)
                self._send_json({"ok": True, "torque": amps})
            elif self.path == "/api/stop":
                mgr.send_command("stop", 0)
                self._send_json({"ok": True, "stopped": True})
            elif self.path == "/api/clear_fault":
                mgr.send_command("clear_fault", 0)
                self._send_json({"ok": True, "cleared": True})
            elif self.path == "/api/tune":
                params = {}
                for key, (lo, hi) in TUNE_LIMITS.items():
                    if key in body:
                        v = _finite(body[key], key)
                        if not lo <= v <= hi:
                            raise ValueError(f"{key} mimo rozsahu <{lo}, {hi}>")
                        params[key] = v
                applied, warns = mgr.request_tuning(params)
                self._send_json({"ok": True, "tuning": applied, "warnings": warns})
            else:
                self.send_error(404, "Endpoint nenajdeny")
        except ValueError as err:
            self._send_json({"ok": False, "error": str(err)}, 400)

    def _origin_ok(self):
        """Blokuje cross-site POST (CSRF): Origin, ak je poslany, musi sedniet s Host."""
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin.split("://", 1)[-1] == host

    def _send_json(self, data, status=200):
        resp = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)

    def _send_csv(self):
        if not self.manager:
            self.send_error(503, "Manager nedostupny")
            return
        lines = ["seq,tx_time,rx_time,lat_us,lat_ms,theta_m1_deg,theta_m2_deg,err_deg,speed_rpm,status\n"]
        with self.manager.lock:
            history = list(self.manager.csv_history)
        for p in history:
            lines.append(f"{p['seq']},{p['tx_time']},{p['rx_time']},{p['lat_us']},{p['lat_ms']},{p['theta_m1']},{p['theta_m2']},{p['err_deg']},{p['speed_rpm']},{p['status']}\n")
        csv_bytes = "".join(lines).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="tsn_timing_log.csv"')
        self.send_header("Content-Length", str(len(csv_bytes)))
        self.end_headers()
        self.wfile.write(csv_bytes)

    def log_message(self, format, *args):
        # Potlacenie floodovania konzoly pre /api/status polling
        try:
            msg = format % args
            if "/api/status" in msg or "/favicon.ico" in msg:
                return
            sys.stderr.write(f"{self.address_string()} - - [{self.log_date_time_string()}] {msg}\n")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="KD240 TSN Synchronizacny Web Dashboard")
    parser.add_argument("--mode", choices=["demo", "sender", "receiver", "single"], default="demo",
                        help="Rezim servera: demo (simulacia 2 motorov), sender, receiver, single (jeden motor)")
    parser.add_argument("--backend", choices=["sim", "foc_lib"], default=None,
                        help="Backend motora (default: sim pre demo, foc_lib pre sender/receiver)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument("--host", default=None,
                        help="Listen adresa (default: 127.0.0.1 pre demo, 0.0.0.0 pre rezimy s motorom)")
    parser.add_argument("--config", default=None, help="Cesta ku konfiguracnemu toml")

    args = parser.parse_args()

    if args.host is None:
        args.host = "127.0.0.1" if args.mode == "demo" else "0.0.0.0"
    # Nastav backend
    if args.backend is None:
        args.backend = "sim" if args.mode == "demo" else "foc_lib"

    print("=" * 65)
    print("      KD240 TSN SYNC — MODERN WEB DASHBOARD & CONTROLLER      ")
    print("=" * 65)
    print(f"Rezim:   {args.mode.upper()}")
    print(f"Backend: {args.backend}")
    print(f"Server:  http://{args.host}:{args.port}")
    if args.host not in ("127.0.0.1", "localhost"):
        print("POZOR:   dashboard nema autentifikaciu, ovlada motor komukolvek v sieti. "
              "Pouzi len v doveryhodnej sieti (Tailscale/TSN).")
    print("=" * 65)

    manager = SystemManager(mode=args.mode, backend=args.backend, cfg_path=args.config)
    manager.start()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.manager = manager
    try:
        print(f"\nDashboard bezi! Otvor v prehliadaci: http://localhost:{args.port} (alebo IP dosky)")
        print("Pre ukoncenie stlac Ctrl+C\n")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUkoncujem server...")
    finally:
        manager.stop()
        server.server_close()
        print("Server zastaveny.")


if __name__ == "__main__":
    main()
