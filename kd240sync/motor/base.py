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

    def set_voltage_v(self, volts: float):
        """Priame napatie Vq (open-loop V/f). Nie je to povinne pre kazdy backend."""
        raise NotImplementedError(f"backend {self.name} nepodporuje napatovy rezim")

    @abstractmethod
    def stop(self):
        """Bezpecny stav: nulovy moment, motor sa uvolni (rezim Off)."""
