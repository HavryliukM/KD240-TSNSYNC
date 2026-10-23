"""Spolocne rozhranie motora. Sender a receiver pracuju len cez toto rozhranie."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MotorState:
    t_ns: int           # cas merania (monotonic)
    theta_deg: float    # uhol tak, ako ho dava zdroj (0..360 alebo viacotackovy)
    speed_rpm: float    # otacky


class Motor(ABC):
    name = "base"

    def open(self):
        pass

    def close(self):
        pass

    @abstractmethod
    def read(self) -> MotorState: ...

    @abstractmethod
    def set_speed_rpm(self, rpm: float): ...

    @abstractmethod
    def set_torque_a(self, amps: float): ...

    @abstractmethod
    def stop(self):
        """Bezpecny stav: nulovy moment, motor sa uvolni (rezim Off)."""
