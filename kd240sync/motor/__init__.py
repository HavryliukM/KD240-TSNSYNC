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
        return FocLibMotor(module=cfg.motor.foc_lib.module)
    raise ValueError(f"neznamy motor.backend: {kind}")
