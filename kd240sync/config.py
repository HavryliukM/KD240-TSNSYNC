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
    "safety": {
        # Model sustavy pre overenie stability zosilneni (Ka = kt/J, rad/s^2 na 1 A).
        # V simulacii 2500; na realnom motore ODMERAT (README, Ladenie regulatora).
        "ka_rad_s2_per_a": 2500.0,
        "ka_lo": 0.5,             # zosilnenia musia byt stabilne pre Ka v [lo, hi] * Ka
        "ka_hi": 2.0,
        "tau_i_s": 0.002,         # odhad casovej konstanty prudovej slucky
        "max_torque_a": 2.0,      # tvrdy strop limitu momentu, ktory sa da nastavit
        "max_slew_a_s": 1000.0,
        "max_error_cap_deg": 180.0,
        "spike_deg": 45.0,        # skokova zmena chyby za jeden cyklus -> FAULT
        "sat_s": 0.6,             # vystup nasyteny dlhsie nez toto pri chybe > 5 deg -> FAULT
        "osc_amp_deg": 4.0,       # kmitanie: aspon osc_flips zmien znamienka za 1 s
        "osc_flips": 14,
        "overrun_factor": 20.0,   # vypadok cyklu dlhsi nez N periodam -> FAULT
        "overspeed_factor": 1.25, # nad sender.max_rpm * faktor -> FAULT
    },
    "sim_net": {
        # Model TSN linky len pre demo v dashboarde (realna siet sa neovplyvnuje)
        "delay_us": 150.0,        # typicke jednosmerne oneskorenie
        "jitter_us": 25.0,        # smerodajna odchylka
        "spike_prob": 0.002,      # pravdepodobnost oneskoreneho paketu
        "spike_us": 1500.0,       # dodatocne oneskorenie pri spike
        "loss": 0.0,              # pravdepodobnost straty paketu
    },
    "sender": {
        "rate_hz": 200.0,
        "initial_rpm": 0.0,
        "max_rpm": 2000.0,
        "ramp_rpm_s": 500.0,      # max. zrychlenie ziadanej rychlosti, 0 = bez rampy
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
        # Zosilnenia musia prejst overenim stability v kd240sync/safety.py (inak sa znizia).
        # Kp = moment [A] na stupen chyby; Kd = tlmenie na rychlostnu chybu
        # Na realnej doske zacni s kp 0.011 a kd 0.00045
        "torque_pd": {"kp_a_per_deg": 0.022, "kd_a_per_dps": 0.00045,
                      "ki_a_per_deg_s": 0.02, "i_limit_a": 0.15,
                      "deadband_deg": 0.1,      # ~1 impulz enkodera; 0 = vypnute
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
