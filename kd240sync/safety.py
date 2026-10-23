"""Bezpecnostna vrstva regulatora polohy: obmedzenie zosilneni a dohlad nad behom.

1) clamp_gains(): zosilnenia PD(I) sa pred pouzitim overia na modeli sustavy
   (dvojity integrator so ziskom Ka, oneskorenie 1 vzorka, prudova slucka 1. radu).
   Ak by zosilnenia pri ktoromkolvek Ka z rozsahu [Ka*ka_lo, Ka*ka_hi] nezaruchovali
   stabilitu, skalovane sa dolu. Ziadne nastavenie z dashboardu tak nemoze
   model-teoreticky rozkmitat slucku. Zaruka plati len pre model; Ka treba odmerat
   (safety.ka_rad_s2_per_a), kym nie je odmerane, je to odhad.

2) Supervisor: kontroluje kazdy cyklus a pri anomalii vrati dovod poruchy
   (volajuci musi motor zastavit): neciselne hodnoty, velka chyba, skokova zmena
   chyby (spike), dlhe nasyteny vystup, kmitanie, prekrocenie rychlosti, vypadok cyklu.
"""
import math
from collections import deque

_DEG = 180.0 / math.pi


def _charpoly(m):
    """Koeficienty [1, c1..cn] charakteristickeho polynomu matice (Faddeev-LeVerrier)."""
    n = len(m)
    coef = [1.0]
    mk = [[0.0] * n for _ in range(n)]
    for k in range(1, n + 1):
        # mk = m * (mk + c_{k-1} I)
        t = [[mk[i][j] + (coef[-1] if i == j else 0.0) for j in range(n)] for i in range(n)]
        mk = [[sum(m[i][l] * t[l][j] for l in range(n)) for j in range(n)] for i in range(n)]
        coef.append(-sum(mk[i][i] for i in range(n)) / k)
    return coef


def _schur_stable(coef, radius=1.0):
    """True, ak vsetky korene polynomu lezia v kruhu |z| < radius (Schur-Cohn)."""
    a = [c * radius ** (len(coef) - 1 - i) for i, c in enumerate(coef)]
    a = [c / a[0] for c in a]
    while len(a) > 1:
        k = a[-1]
        if not math.isfinite(k) or abs(k) >= 1.0:
            return False
        n = len(a) - 1
        a = [1.0] + [(a[i] - k * a[n - i]) / (1.0 - k * k) for i in range(1, n)]
    return True


def _stable(kp, kd, ki, ka, dt, tau_i, margin=0.97):
    """Stabilita uzavretej slucky e'' = -ka*i_m, i_m = prudova slucka 1. radu so zpozdenim
    1 vzorka, u = PD(I). Stav: [e, w, integral, i_m, u_prev]; kp [A/deg], kd [A/(deg/s)],
    ki [A/(deg*s)]. Vsetky polove spektra musia mat modul < margin."""
    kp_r, kd_r, ki_r = kp * _DEG, kd * _DEG, ki * _DEG
    alpha = 1.0 if tau_i <= 0 else 1.0 - math.exp(-dt / tau_i)
    u = [kp_r, kd_r, ki_r, 0.0, 0.0]                                   # u z povodneho stavu
    im = [0.0, 0.0, 0.0, 1.0 - alpha, alpha]                           # novy i_m
    a_ = [-ka * x for x in im]                                         # zrychlenie
    e_n = [1.0 + 0.5 * dt * dt * a_[0], dt + 0.5 * dt * dt * a_[1], 0.5 * dt * dt * a_[2],
           0.5 * dt * dt * a_[3], 0.5 * dt * dt * a_[4]]
    w_n = [dt * a_[0], 1.0 + dt * a_[1], dt * a_[2], dt * a_[3], dt * a_[4]]
    int_n = [dt * e_n[0], dt * e_n[1], 1.0 + dt * e_n[2], dt * e_n[3], dt * e_n[4]]
    m = [e_n, w_n, int_n, im, u]
    if not all(math.isfinite(x) for r in m for x in r):
        return False
    return _schur_stable(_charpoly(m), 1.0 / margin)


def robust_stable(kp, kd, ki, dt, ka, ka_lo=0.5, ka_hi=2.0, tau_i=0.002, n=None):
    return all(_stable(kp, kd, ki, ka * f, dt, tau_i) for f in (ka_lo, 1.0, ka_hi))


def clamp_gains(kp, kd, ki, limit_a, slew_a_s, max_err_deg, dt, sc):
    """Vrati (hodnoty, varovania). sc = cfg.safety (Cfg)."""
    warns = []
    kp, kd, ki = (max(0.0, float(x)) for x in (kp, kd, ki))
    ki = min(ki, 2.0 * kp)                      # integrator nesmie dominovat nad P
    ka = float(sc.ka_rad_s2_per_a)
    lo, hi, tau_i = float(sc.ka_lo), float(sc.ka_hi), float(sc.tau_i_s)
    k0 = (kp, kd, ki)
    kd = min(kd, 0.7 / (ka * hi * dt * _DEG))   # derivacny clen nesmie byt vacsi nez 1 vzorka tlmenia
    if not robust_stable(kp, kd, ki, dt, ka, lo, hi, tau_i):
        # zosilnenia sa znizuju po krokoch (stabilna oblast nie je v skale monotonna),
        # kd je uz obmedzene; ak nic nevyhovie, ostane 0 (motor sa neriadi)
        kp0, ki0 = kp, ki
        kp = ki = 0.0
        for k in range(1, 80):
            m = 0.85 ** k
            if robust_stable(kp0 * m, kd, ki0 * m, dt, ka, lo, hi, tau_i):
                kp, ki = kp0 * m, ki0 * m
                break
    if (kp, kd, ki) != k0:
        warns.append("zosilnenia znizene na stabilny rozsah "
                     f"(Kp={kp:.4f}, Kd={kd:.5f}, Ki={ki:.5f})")
    cap = float(sc.max_torque_a)
    if limit_a > cap:
        limit_a = cap
        warns.append(f"limit momentu znizeny na {cap} A")
    cap = float(sc.max_slew_a_s)
    if slew_a_s > cap:
        slew_a_s = cap
        warns.append(f"slew znizeny na {cap:.0f} A/s")
    cap = float(sc.max_error_cap_deg)
    if max_err_deg > cap:
        max_err_deg = cap
        warns.append(f"limit chyby znizeny na {cap:.0f} deg")
    return {"kp": kp, "kd": kd, "ki": ki, "torque_limit_a": limit_a,
            "slew_a_s": slew_a_s, "max_error_deg": max_err_deg}, warns


class Supervisor:
    """Dohlad nad regulaciou. check() vola receiver v kazdom cykle v stave RUN."""

    def __init__(self, sc, period_s, max_err_deg, overspeed_rpm):
        self.sc = sc
        self.period = float(period_s)
        self.max_err = float(max_err_deg)
        self.overspeed = float(overspeed_rpm)
        self.reset()

    def reset(self):
        self._prev_err = None
        self._sat_s = 0.0
        self._flips = deque()
        self._sign = 0
        self._last_t = None

    def check(self, now_s, err, out, limit_a, speed_rpm):
        """Vrati retazec s dovodom poruchy alebo None."""
        sc = self.sc
        if not all(math.isfinite(x) for x in (err, out, speed_rpm)):
            return "neciselna hodnota v regulacii"
        if abs(err) > self.max_err:
            return f"chyba polohy {err:+.1f} deg > {self.max_err:.0f} deg"
        if abs(speed_rpm) > self.overspeed:
            return f"prekrocena rychlost {speed_rpm:.0f} rpm > {self.overspeed:.0f} rpm"
        if self._last_t is not None:
            gap = now_s - self._last_t
            if gap > float(sc.overrun_factor) * self.period:
                self._last_t = now_s
                self._prev_err = None
                return f"vypadok regulacnej slucky {gap * 1e3:.0f} ms"
        dt = self.period if self._last_t is None else max(now_s - self._last_t, 1e-6)
        self._last_t = now_s
        if self._prev_err is not None and abs(err - self._prev_err) > float(sc.spike_deg):
            return f"skok chyby {err - self._prev_err:+.1f} deg v jednom cykle"
        self._prev_err = err
        # dlhodobe nasytenie vystupu pri nenulovej chybe = regulator to nezvlada
        if limit_a > 0 and abs(out) >= 0.98 * limit_a and abs(err) > 5.0:
            self._sat_s += dt
            if self._sat_s > float(sc.sat_s):
                return f"vystup nasyteny {self._sat_s:.1f} s pri chybe {err:+.1f} deg"
        else:
            self._sat_s = 0.0
        # kmitanie: casté zmeny znamienka chyby s vyznamnou amplitudou
        if abs(err) > float(sc.osc_amp_deg):
            sign = 1 if err > 0 else -1
            if self._sign and sign != self._sign:
                self._flips.append(now_s)
            self._sign = sign
        while self._flips and now_s - self._flips[0] > 1.0:
            self._flips.popleft()
        if len(self._flips) >= int(sc.osc_flips):
            return "kmitanie regulatora (rychle striedanie znamienka chyby)"
        return None
