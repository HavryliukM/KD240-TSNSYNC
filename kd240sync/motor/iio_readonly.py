"""Len citanie enkodera cez IIO sysfs (zariadenie hls_qei_axi). Motor sa neovlada.

NEOVERENE na hardvery: nazvy suborov v sysfs sa hladaju podla vzoru in_rot0*_raw
(rpm) a in_rot1*_raw (theta_degree). Predtym spusti tools/check_encoder.py a over,
ze sa hodnota meni pri otacani hriadela rukou. Pri prvom pokuse iio_attr ukazoval
raw = 0 aj ked dashboard ukazoval polohu, takze tento backend nemusi fungovat.
Hodi sa, ak chces testovat prenos polohy len s rucne otacanym motorom.
"""
import glob
import os
import time

from .base import Motor, MotorState

IIO_ROOT = "/sys/bus/iio/devices"


def find_device(name="hls_qei_axi"):
    for d in sorted(glob.glob(os.path.join(IIO_ROOT, "iio:device*"))):
        try:
            with open(os.path.join(d, "name")) as f:
                if f.read().strip() == name:
                    return d
        except OSError:
            continue
    return None


def _read_num(path):
    with open(path) as f:
        return float(f.read().strip())


class IioReadOnlyMotor(Motor):
    name = "iio_readonly"

    def __init__(self, device_name="hls_qei_axi"):
        self.device_name = device_name
        self._dev = None
        self._rpm = None
        self._theta = None
        self._rpm_scale = 1.0
        self._theta_scale = 1.0

    def _pick(self, pattern):
        hits = sorted(glob.glob(os.path.join(self._dev, pattern)))
        return hits[0] if hits else None

    def open(self):
        self._dev = find_device(self.device_name)
        if not self._dev:
            raise RuntimeError(f"IIO zariadenie {self.device_name} nenajdene "
                               "(je nacitany firmware kd240-motor-ctrl-qei?)")
        self._rpm = self._pick("in_rot0*_raw")
        self._theta = self._pick("in_rot1*_raw")
        if not self._rpm or not self._theta:
            raise RuntimeError("nenasli sa subory in_rot0*_raw / in_rot1*_raw, "
                               f"pozri obsah {self._dev} (tools/check_encoder.py)")
        for attr, path in (("_rpm_scale", self._rpm), ("_theta_scale", self._theta)):
            sc = path[:-len("raw")] + "scale"
            if os.path.exists(sc):
                setattr(self, attr, _read_num(sc))

    def read(self) -> MotorState:
        th = _read_num(self._theta) * self._theta_scale
        w = _read_num(self._rpm) * self._rpm_scale
        return MotorState(time.monotonic_ns(), th, w)

    def set_speed_rpm(self, rpm):
        raise RuntimeError("iio_readonly: motor sa neda ovladat")

    def set_torque_a(self, amps):
        raise RuntimeError("iio_readonly: motor sa neda ovladat")

    def stop(self):
        pass
