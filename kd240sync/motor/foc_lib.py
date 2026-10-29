"""Adapter na motorovu kniznicu AMD (C++ pybind11 modul py_foc_motor_ctrl).

Kniznica sa nachadza v:
  /opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib/
poskytuje modul `py_foc_motor_ctrl` (pripadne `py_motor_control`).

Rozhranie:
  - MotorControl.getMotorControlInstance(sessionId=1)
  - mc.setOperationMode(MotorOpMode.kModeSpeed / kModeTorque / kModeOff)
  - mc.setSpeed(rpm)
  - mc.setTorque(amps)   # rozsah -2.5 az 2.5 A
  - mc.getPosition()     # v stupnoch (degrees)
  - mc.getSpeed()        # v otackach za minutu (rpm)
  - mc.clearFaults()
"""
import importlib
import logging
import sys
import time

from .base import Motor, MotorState

log = logging.getLogger(__name__)

LIB_DIR = "/opt/xilinx/xlnx-app-kd240-foc-motor-ctrl/lib"
CANDIDATE_MODULES = ("py_foc_motor_ctrl", "py_motor_control")
MAX_TORQUE_A = 2.5


class FocLibMotor(Motor):
    name = "foc_lib"

    def __init__(self, module="", config_path=None):
        self.module_name = module
        self.config_path = config_path
        self._lib = None
        self._mc = None
        self._current_mode = None

    def open(self):
        if LIB_DIR not in sys.path:
            sys.path.insert(0, LIB_DIR)

        mod = None
        targets = [self.module_name] if self.module_name else CANDIDATE_MODULES
        errors = []
        for name in targets:
            try:
                mod = importlib.import_module(name)
                self.module_name = name
                break
            except ImportError as err:
                errors.append(f"{name}: {err}")

        if mod is None:
            raise RuntimeError(
                f"Nepodarilo sa importovat motorovy modul ({', '.join(errors)}). "
                f"Uisti sa, ze bezi na doske KD240 s aplikaciou xlnx-app-kd240-foc-motor-ctrl "
                f"alebo pouzi backend 'sim'."
            )

        self._lib = mod

        # Ziskanie singleton instancie MotorControl (session ID = 1)
        try:
            if self.config_path:
                self._mc = mod.MotorControl.getMotorControlInstance(1, self.config_path)
            else:
                self._mc = mod.MotorControl.getMotorControlInstance(1)
        except Exception as err:
            raise RuntimeError(f"Chyba pri inicializacii MotorControl: {err}") from err

        if self._mc is None:
            raise RuntimeError(
                "MotorControl.getMotorControlInstance(1) vratil None. "
                "Skontroluj firmver (xmutil loadapp kd240-motor-ctrl-qei) a 24V napajanie."
            )

        # Vymaz pripadne chyby z minula a daj motor do bezpecneho stavu
        try:
            self._mc.clearFaults()
        except Exception:
            pass

        self.stop()

    def read(self) -> MotorState:
        if self._mc is None:
            raise RuntimeError("Motor nie je otvoreny (zavolaj open())")
        t_ns = time.monotonic_ns()
        theta = float(self._mc.getPosition())
        speed = float(self._mc.getSpeed())
        return MotorState(t_ns, theta, speed)

    def set_speed_rpm(self, rpm: float):
        if self._mc is None:
            raise RuntimeError("Motor nie je otvoreny")
        target_mode = self._lib.MotorOpMode.kModeSpeed
        if self._current_mode != target_mode:
            self._mc.setOperationMode(target_mode)
            self._current_mode = target_mode
        self._mc.setSpeed(float(rpm))

    def set_torque_a(self, amps: float):
        if self._mc is None:
            raise RuntimeError("Motor nie je otvoreny")
        # Bezpecnostne obmedzenie prudu
        clamped = max(-MAX_TORQUE_A, min(MAX_TORQUE_A, float(amps)))
        target_mode = self._lib.MotorOpMode.kModeTorque
        if self._current_mode != target_mode:
            self._mc.setOperationMode(target_mode)
            self._current_mode = target_mode
        self._mc.setTorque(clamped)

    def set_openloop_vq(self, volts: float):
        """Pokusny open-loop V/f rezim: priame napatie Vq bez rampy momentu (len na diagnostiku)."""
        if self._mc is None:
            raise RuntimeError("Motor nie je otvoreny")
        target_mode = self._lib.MotorOpMode.kModeOpenLoop
        if self._current_mode != target_mode:
            self._mc.setOperationMode(target_mode)
            self._current_mode = target_mode
        self._mc.setVfParamVq(float(volts))

    def debug_read(self) -> dict:
        """Diagnostika z kniznice: nastaveny moment a skutocny prud i_q/i_d (len co kniznica ponuka)."""
        out = {}
        if self._mc is None:
            return out
        try:
            out["torque_set"] = float(self._mc.getTorqueSetValue())
        except Exception:
            pass
        try:
            foc = self._mc.getFocCalc()
            out["i_q"] = float(foc.i_q)
            out["i_d"] = float(foc.i_d)
        except Exception:
            pass
        return out

    def stop(self):
        """Uvedie motor do bezpecneho volneho stavu (kModeOff)."""
        if self._mc is not None and self._lib is not None:
            try:
                self._mc.setOperationMode(self._lib.MotorOpMode.kModeOff)
            except Exception:
                pass
            self._current_mode = self._lib.MotorOpMode.kModeOff

    def close(self):
        self.stop()

    def clear_faults(self):
        """Vymaze poruchove stavy v kniznici."""
        if self._mc is not None:
            self._mc.clearFaults()

    def get_fault_status(self) -> dict:
        """Vrati slovnik so stavom poruch."""
        if self._mc is None or self._lib is None:
            return {}
        faults = {}
        for attr in dir(self._lib.FaultId):
            if attr.startswith("k") and not attr.endswith("Max"):
                fault_enum = getattr(self._lib.FaultId, attr)
                try:
                    faults[attr] = bool(self._mc.getFaultStatus(fault_enum))
                except Exception:
                    pass
        return faults
