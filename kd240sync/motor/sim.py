"""Simulovany motor na testovanie bez hardveru.

Model: J*dw/dt = kt*i - b*w - coulomb*tanh(w/0.5). Rezim 'speed' je zjednoduseny
(prvy rad + obmedzenie zrychlenia), rezim 'torque' pouziva ziadany prud priamo.
Parametre su orientacne, NEPOCHADZAJU z mereni skutocneho motora.
"""
import math
import threading
import time

from .base import Motor, MotorState


class SimMotor(Motor):
    name = "sim"

    def __init__(self, J=2e-5, kt=0.05, b=1e-5, coulomb=5e-4, tau_speed=0.05,
                 accel_limit_rpm_s=20000.0, counts_per_rev=4096,
                 initial_theta_deg=0.0, clock=time.monotonic_ns):
        self.J, self.kt, self.b, self.coulomb = J, kt, b, coulomb
        self.tau_speed = tau_speed
        self.acc_lim = accel_limit_rpm_s * 2 * math.pi / 60.0
        self.counts = counts_per_rev
        self._clock = clock
        self._lock = threading.Lock()
        self.theta = math.radians(initial_theta_deg)
        self.omega = 0.0
        self.mode = "off"
        self.omega_set = 0.0
        self.i_set = 0.0
        self._last = clock()

    def _advance(self):
        now = self._clock()
        dt = (now - self._last) / 1e9
        self._last = now
        if dt <= 0:
            return
        n = max(1, int(math.ceil(dt / 0.001)))
        h = dt / n
        for _ in range(n):
            if self.mode == "speed":
                dw = (self.omega_set - self.omega) / self.tau_speed
                dw = max(-self.acc_lim, min(self.acc_lim, dw))
                self.omega += dw * h
            else:
                tq = self.kt * self.i_set if self.mode == "torque" else 0.0
                fr = self.b * self.omega + self.coulomb * math.tanh(self.omega / 0.5)
                self.omega += (tq - fr) / self.J * h
            self.theta += self.omega * h

    def read(self) -> MotorState:
        with self._lock:
            self._advance()
            raw = math.degrees(self.theta) % 360.0
            q = 360.0 / self.counts
            raw = round(raw / q) * q % 360.0
            return MotorState(self._last, raw, self.omega * 60.0 / (2 * math.pi))

    def set_speed_rpm(self, rpm):
        with self._lock:
            self._advance()
            self.mode = "speed"
            self.omega_set = rpm * 2 * math.pi / 60.0

    def set_torque_a(self, amps):
        with self._lock:
            self._advance()
            self.mode = "torque"
            self.i_set = float(amps)

    def stop(self):
        with self._lock:
            self._advance()
            self.mode = "off"
            self.i_set = 0.0
            self.omega_set = 0.0

    def turn_by_hand(self, deg):
        """Pomocna funkcia pre testy: posun hriadela o 'deg' stupnov."""
        with self._lock:
            self.theta += math.radians(deg)
