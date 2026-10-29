"""Polohove regulatory pre motor 2. Jednotky: stupne, stupne/s, ampery."""


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


class TorquePD:
    """Polohovy PD(I) regulator s vystupom = moment (prud v A).

    u = kp*e + kd*(w_ref - w) + kff*w_ref + integral(ki*e), s limitom a obmedzenim rychlosti zmeny.

    Rovnaka trieda sluzi aj pre napatovy rezim (voltage_pd): jednotky vystupu su potom volty.
    """

    def __init__(self, kp, kd, ki=0.0, limit_a=0.3, slew_a_s=50.0, i_limit_a=0.05, deadband_deg=0.0,
                 kff=0.0):
        self.kp, self.kd, self.ki, self.kff = kp, kd, ki, kff
        self.deadband = float(deadband_deg)
        self.limit, self.slew, self.i_limit = limit_a, slew_a_s, i_limit_a
        self.reset()

    def reset(self):
        self.integ = 0.0
        self.out = 0.0

    def update(self, e_deg, w_err_dps, dt, w_ref_dps=0.0):
        # mala mrtva zona okolo nuly: kvantovanie enkodera by inak v kluzi vyrabalo
        # trvale mikro-kmity momentu (motor sa 'chvie' na -0.1 rpm)
        e_raw = e_deg
        if self.deadband > 0.0:
            e_deg -= max(-self.deadband, min(self.deadband, e_deg))
            if e_deg == 0.0 and abs(w_err_dps) < 1.0:
                w_err_dps = 0.0
        u = self.kp * e_deg + self.kd * w_err_dps + self.kff * w_ref_dps
        if self.ki:
            # integrator pracuje s nezmensenou chybou: P-clen v mrtvej zone je prilis slaby
            # na prekonanie trenia, a prave integrator musi zvysnu odchylku dotiahnut na nulu
            cand = _clamp(self.integ + self.ki * e_raw * dt, -self.i_limit, self.i_limit)
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


class RampLimiter:
    """Obmedzuje zrychlenie ziadanej rychlosti [rpm/s], aby skok nezhodil sledovanie."""

    def __init__(self, rate_rpm_s, value=0.0):
        self.rate = float(rate_rpm_s)
        self.target = self.value = float(value)

    def set_target(self, rpm):
        self.target = float(rpm)

    def jump(self, rpm=0.0):
        """Okamzite nastavenie (napr. po STOP), bez rampy."""
        self.target = self.value = float(rpm)

    def update(self, dt):
        if self.rate <= 0:                      # 0 = rampa vypnuta
            self.value = self.target
            return self.value
        step = self.rate * dt
        self.value += max(-step, min(step, self.target - self.value))
        return self.value
