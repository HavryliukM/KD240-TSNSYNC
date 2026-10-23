import sys
import types
import unittest

from kd240sync.motor.foc_lib import FocLibMotor


class DummyOpMode:
    kModeOff = 0
    kModeSpeed = 1
    kModeTorque = 2


class DummyMotorControl:
    instance = None

    def __init__(self):
        self.mode = DummyOpMode.kModeOff
        self.speed = 0.0
        self.pos = 45.0
        self.torque = 0.0
        self.faults_cleared = False

    @classmethod
    def getMotorControlInstance(cls, session_id, config_path=None):
        if cls.instance is None:
            cls.instance = DummyMotorControl()
        return cls.instance

    def setOperationMode(self, mode):
        self.mode = mode

    def setSpeed(self, speed):
        self.speed = speed

    def setTorque(self, torque):
        self.torque = torque

    def getSpeed(self):
        return self.speed

    def getPosition(self):
        return self.pos

    def clearFaults(self):
        self.faults_cleared = True


class FocLibTests(unittest.TestCase):
    def setUp(self):
        DummyMotorControl.instance = None
        # Vytvorime mock modul py_foc_motor_ctrl
        self.mock_mod = types.ModuleType("py_foc_motor_ctrl")
        self.mock_mod.MotorControl = DummyMotorControl
        self.mock_mod.MotorOpMode = DummyOpMode
        self.mock_mod.FaultId = types.SimpleNamespace(kPhaseA_OC=1, kFaultIdMax=2)
        sys.modules["py_foc_motor_ctrl"] = self.mock_mod

    def tearDown(self):
        sys.modules.pop("py_foc_motor_ctrl", None)

    def test_open_and_read(self):
        m = FocLibMotor(module="py_foc_motor_ctrl")
        m.open()
        self.assertEqual(m._mc.mode, DummyOpMode.kModeOff)
        self.assertTrue(m._mc.faults_cleared)

        st = m.read()
        self.assertEqual(st.theta_deg, 45.0)
        self.assertEqual(st.speed_rpm, 0.0)

    def test_speed_control(self):
        m = FocLibMotor(module="py_foc_motor_ctrl")
        m.open()
        m.set_speed_rpm(500.0)
        self.assertEqual(m._mc.mode, DummyOpMode.kModeSpeed)
        self.assertEqual(m._mc.speed, 500.0)
        self.assertEqual(m.read().speed_rpm, 500.0)

    def test_torque_control_and_clamp(self):
        m = FocLibMotor(module="py_foc_motor_ctrl")
        m.open()
        m.set_torque_a(0.15)
        self.assertEqual(m._mc.mode, DummyOpMode.kModeTorque)
        self.assertEqual(m._mc.torque, 0.15)

        # Prekrocenie limitu 2.5 A -> clamp
        m.set_torque_a(10.0)
        self.assertEqual(m._mc.torque, 2.5)
        m.set_torque_a(-10.0)
        self.assertEqual(m._mc.torque, -2.5)

    def test_stop(self):
        m = FocLibMotor(module="py_foc_motor_ctrl")
        m.open()
        m.set_speed_rpm(300.0)
        m.stop()
        self.assertEqual(m._mc.mode, DummyOpMode.kModeOff)


if __name__ == "__main__":
    unittest.main()
