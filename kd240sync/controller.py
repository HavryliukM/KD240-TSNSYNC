"""Polohove regulatory pre motor 2. Jednotky: stupne, stupne/s, ampery."""


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class TorquePD:
    """Polohovy PD(I) regulator s vystupom = moment (prud v A).

    u = kp*e + kd*(w_ref - w) + integral(ki*e), s limitom a obmedzenim rychlosti zmeny.
    """

    def __init__(self, kp, kd, ki=0.0, limit_a=0.3, slew_a_s=50.0, i_limit_a=0.05):
        self.kp, self.kd, self.ki = kp, kd, ki
        self.limit, self.slew, self.i_limit = limit_a, slew_a_s, i_limit_a
        self.reset()

    def reset(self):
        self.integ = 0.0
        self.out = 0.0

    def update(self, e_deg, w_err_dps, dt):
        u = self.kp * e_deg + self.kd * w_err_dps
        if self.ki:
            cand = _clamp(self.integ + self.ki * e_deg * dt, -self.i_limit, self.i_limit)
            if abs(u + cand) <= self.limit:   # anti-windup: integruj len mimo saturacie
                self.integ = cand
            u += self.integ
        u = _clamp(u, -self.limit, self.limit)
        step = self.slew * dt
        self.out = _clamp(u, self.out - step, self.out + step)
        return self.out


class SpeedP:
    """Kaskada: polohova chyba -> ziadana rychlost (rpm) pre rychlostnu slucku kniznice."""

    def __init__(self, kp_rpm_per_deg, max_rpm):
        self.kp, self.max_rpm = kp_rpm_per_deg, max_rpm
        self.out = 0.0

    def reset(self):
        self.out = 0.0

    def update(self, e_deg, w_ff_dps, dt):
        rpm = w_ff_dps / 6.0 + self.kp * e_deg
        self.out = _clamp(rpm, -self.max_rpm, self.max_rpm)
        return self.out
