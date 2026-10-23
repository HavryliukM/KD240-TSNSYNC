"""Nacitanie konfiguracie z TOML (Python 3.11+ ma tomllib v standardnej kniznici)."""
import copy
import tomllib

DEFAULTS = {
    "network": {
        "bind_ip": "127.0.0.1",   # lokalna adresa (na doske: ep.20, napr. 111.222.0.10)
        "peer_ip": "127.0.0.1",   # sender: adresa receivera
        "port": 5005,
        "so_priority": -1,        # -1 = nenastavovat (master mapuje prioritu 0 -> PCP 4)
    },
    "motor": {
        "backend": "sim",         # sim | foc_lib | iio_readonly
        "foc_lib": {"module": ""},
        "sim": {"J": 2e-5, "kt": 0.05, "b": 1e-5, "coulomb": 5e-4,
                "tau_speed": 0.05, "accel_limit_rpm_s": 20000.0,
                "counts_per_rev": 4096},
    },
    "sender": {
        "rate_hz": 200.0,
        "initial_rpm": 0.0,
        "max_rpm": 2000.0,
        "min_rpm_warn": 250.0,    # pod tuto rychlost sa motor nemusi rozbehnut
        "spin_us": 0,
        "log_path": "",
    },
    "receiver": {
        "rate_hz": 200.0,
        "timeout_ms": 50.0,
        "direction": 1,           # +1 rovnaky smer, -1 opacny
        "ratio": 1.0,             # prevod (elektronicky prevod)
        "max_error_deg": 90.0,    # nad touto chybou -> FAULT a motor sa uvolni
        "mode": "torque_pd",      # torque_pd | speed_p
        "spin_us": 0,
        "log_path": "",
        "status_period_s": 1.0,
        # Vyladene parametre pre simulaciu (200 Hz, SimMotor):
        # Kp = moment [A] na stupen chyby; Kd = tlmenie na rychlostnu chybu
        # Na realnej doske treba znizit kp na 0.011 a kd na 0.00045
        "torque_pd": {"kp_a_per_deg": 0.08, "kd_a_per_dps": 0.002,
                      "ki_a_per_deg_s": 0.002, "i_limit_a": 0.15,
                      "torque_limit_a": 1.5, "slew_a_s": 500.0},
        "speed_p": {"kp_rpm_per_deg": 5.0, "max_rpm": 1500.0},
    },
}


class Cfg(dict):
    """dict s pristupom cez bodku: cfg.receiver.rate_hz"""

    def __getattr__(self, k):
        try:
            v = self[k]
        except KeyError as e:
            raise AttributeError(k) from e
        return Cfg(v) if isinstance(v, dict) else v


def _merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load(path=None, overrides=None) -> Cfg:
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, "rb") as f:
            _merge(cfg, tomllib.load(f))
    if overrides:
        _merge(cfg, overrides)
    return Cfg(cfg)
