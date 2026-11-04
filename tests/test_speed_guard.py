import unittest

from kd240sync import config, position_test
from kd240sync.motor.base import MotorState
from kd240sync.motor.sim import SimMotor
from kd240sync.safety import SpeedGuard
from tests.test_position_test import VirtualLoop


class GlitchyMotor(SimMotor):
    """Simulovany motor, ktory od glitch_at_s vrati na glitch_ms rychlost glitch_rpm (ako kniznica AMD 4. 11. 2026)."""

    def __init__(self, glitch_at_s, glitch_ms=2, glitch_rpm=695.0, **kw):
        super().__init__(**kw)
        self.g0 = int(glitch_at_s * 1e9)
        self.g1 = self.g0 + int(glitch_ms * 1e6)
        self.g_rpm = glitch_rpm

    def read(self):
        ms = super().read()
        if self.g0 <= ms.t_ns < self.g1:
            return MotorState(ms.t_ns, ms.theta_deg, self.g_rpm)
        return ms


class SpeedGuardTests(unittest.TestCase):
    def _guard(self):
        return SpeedGuard(20000.0, 15.0, 0.004, 0.05)

    def _feed(self, g, seq, dt=0.001):
        """seq = [(rpm, theta)], vrati rychlosti pre regulator."""
        return [g.update(i * dt, v, th) for i, (v, th) in enumerate(seq)]

    def test_short_spike_at_standstill_is_ignored(self):
        g = self._guard()
        out = self._feed(g, [(1, 0), (1, 0), (695, 0), (695, 0), (1, 0), (2, 0)])
        self.assertEqual(out, [1, 1, 1, 1, 1, 2])
        self.assertEqual(g.glitches, 1)

    def test_long_spike_without_motion_is_ignored_and_return_accepted(self):
        # 93 rpm na 9 ms pri stojacom motore: predchadzajuca verzia ju prijala a potom drzala
        g = self._guard()
        seq = [(1, 359)] * 3 + [(93, 359)] * 9 + [(2, 359)] * 3
        out = self._feed(g, seq)
        self.assertTrue(all(v <= 2 for v in out), out)
        self.assertEqual(g.glitches, 1)

    def test_real_acceleration_passes(self):
        g = self._guard()
        seq = [(i * 15.0, 0.0) for i in range(40)]         # 15 rpm/ms, pod limitom
        self.assertEqual(self._feed(g, seq), [v for v, _ in seq])
        self.assertEqual(g.glitches, 0)

    def test_real_jump_confirmed_by_position(self):
        # nahly skutocny pohyb 700 rpm = 4.2 deg/ms: prijme sa najneskor po confirm_s
        g = self._guard()
        seq = [(0.0, 0.0)] + [(700.0, 4.2 * (i + 1)) for i in range(8)]
        out = self._feed(g, seq)
        self.assertEqual(out[1], 0.0)
        self.assertEqual(out[-1], 700.0)
        self.assertLessEqual(out.index(700.0), 5)
        self.assertEqual(g.glitches, 0)

    def test_unconfirmed_value_accepted_after_max_hold(self):
        g = self._guard()
        out = self._feed(g, [(0.0, 0.0)] + [(700.0, 0.0)] * 60)
        self.assertEqual(out[30], 0.0)
        self.assertEqual(out[-1], 700.0)                   # dlhsie nez 50 ms sa neda vylucit, rozhodne dohlad

    def test_receiver_rate(self):
        g = self._guard()                                  # 200 Hz: povoleny skok 115 rpm za 5 ms
        out = self._feed(g, [(0.0, 0), (100.0, 1), (695.0, 2), (101.0, 3)], dt=0.005)
        self.assertEqual(out, [0.0, 100.0, 100.0, 101.0])

    def _position_run(self, **glitch):
        cfg = config.load(None, {"receiver": {"mode": "voltage_pd"}})
        loop = VirtualLoop()
        m = GlitchyMotor(1.2, **glitch, **cfg.motor.sim, clock=loop.clock)
        m.open()
        try:
            return position_test.run(cfg, m, [(20.0, 1.5)], settle_s=0.3, log=lambda *_: None, loop=loop)
        finally:
            m.close()

    def test_position_test_survives_library_spikes(self):
        for glitch in ({"glitch_ms": 2, "glitch_rpm": 695.0}, {"glitch_ms": 9, "glitch_rpm": 93.0}):
            res = self._position_run(**glitch)
            self.assertEqual(res["fault"], "", glitch)
            self.assertEqual(res["stats"]["speed_glitches"], 1, glitch)
            self.assertIn(glitch["glitch_rpm"], list(res["data"]["speed_rpm"]))   # v CSV ostane nefiltrovana


if __name__ == "__main__":
    unittest.main()
