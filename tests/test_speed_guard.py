import unittest

from kd240sync import config, position_test
from kd240sync.motor.base import MotorState
from kd240sync.motor.sim import SimMotor
from kd240sync.safety import SpeedGuard
from tests.test_position_test import VirtualLoop


class GlitchyMotor(SimMotor):
    """Simulovany motor, ktory v case glitch_at_s vrati 2 ms rychlost 695 rpm (ako kniznica AMD 4. 11. 2026)."""

    def __init__(self, glitch_at_s, **kw):
        super().__init__(**kw)
        self.glitch_at_ns = int(glitch_at_s * 1e9)

    def read(self):
        ms = super().read()
        if self.glitch_at_ns <= ms.t_ns < self.glitch_at_ns + 2_000_000:
            return MotorState(ms.t_ns, ms.theta_deg, 695.0)
        return ms


class SpeedGuardTests(unittest.TestCase):
    def _guard(self):
        return SpeedGuard(20000.0, 15.0, 0.006)

    def test_single_spike_is_ignored(self):
        g = self._guard()
        out = [g.update(i * 0.001, v) for i, v in enumerate([1, 1, 695, 695, 1, 2])]
        self.assertEqual(out, [1, 1, 1, 1, 1, 2])
        self.assertEqual(g.glitches, 1)

    def test_real_acceleration_passes(self):
        g = self._guard()
        vals = [i * 15.0 for i in range(40)]              # 15 rpm/ms = 15 000 rpm/s, pod limitom
        self.assertEqual([g.update(i * 0.001, v) for i, v in enumerate(vals)], vals)
        self.assertEqual(g.glitches, 0)

    def test_persistent_change_is_accepted_after_hold(self):
        g = self._guard()
        g.update(0.0, 0.0)
        out = [g.update((i + 1) * 0.001, 700.0) for i in range(10)]
        self.assertEqual(out[0], 0.0)
        self.assertEqual(out[-1], 700.0)                   # skutocny rozbeh dohlad uvidi najneskor po hold_s
        self.assertLessEqual(out.index(700.0), 7)

    def test_receiver_rate(self):
        g = self._guard()                                  # 200 Hz: povoleny skok 115 rpm za 5 ms
        self.assertEqual(g.update(0.0, 0.0), 0.0)
        self.assertEqual(g.update(0.005, 100.0), 100.0)
        self.assertEqual(g.update(0.010, 695.0), 100.0)
        self.assertEqual(g.update(0.015, 101.0), 101.0)

    def test_position_test_survives_library_spike(self):
        cfg = config.load(None, {"receiver": {"mode": "voltage_pd"}})
        loop = VirtualLoop()
        m = GlitchyMotor(1.2, **cfg.motor.sim, clock=loop.clock)
        m.open()
        try:
            res = position_test.run(cfg, m, [(20.0, 1.5)], settle_s=0.3, log=lambda *_: None, loop=loop)
        finally:
            m.close()
        self.assertEqual(res["fault"], "")
        self.assertEqual(res["stats"]["speed_glitches"], 1)
        self.assertIn(695.0, list(res["data"]["speed_rpm"]))   # v CSV ostane nefiltrovana hodnota


if __name__ == "__main__":
    unittest.main()
