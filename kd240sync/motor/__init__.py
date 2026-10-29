from .base import Motor, MotorState
from .sim import SimMotor
from .iio_readonly import IioReadOnlyMotor
from .foc_lib import FocLibMotor


def create(cfg) -> Motor:
    kind = cfg.motor.backend
    if kind == "sim":
        return SimMotor(**cfg.motor.sim)
    if kind == "iio_readonly":
        return IioReadOnlyMotor()
    if kind == "foc_lib":
        return FocLibMotor(module=cfg.motor.foc_lib.module,
                           config_path=cfg.motor.foc_lib.get("config_path") or None)
    raise ValueError(f"neznamy motor.backend: {kind}")
