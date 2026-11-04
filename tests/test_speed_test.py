import unittest

from kd240sync import config, speed_test
from kd240sync.motor.sim import SimMotor
from kd240sync.step_metrics import analyze
from tests.test_position_test import VirtualLoop


def run_sim(steps, **kw):
    cfg = config.load(None)
    loop = VirtualLoop(0.0005)
    m = SimMotor(**cfg.motor.sim, clock=loop.clock)
    m.open()
    try:
        return speed_test.run(cfg, m, steps, sample_hz=2000.0, log=lambda *_: None, loop=loop, **kw)
    finally:
        m.close()


class SpeedTestTests(unittest.TestCase):
    def test_steps_reach_target_and_metrics_work_on_speed(self):
        res = run_sim([(300.0, 1.0), (600.0, 1.0), (0.0, 1.0)], settle_s=0.3)
        self.assertEqual(res["fault"], "")
        d = res["data"]
        self.assertEqual(set(d), set(speed_test.COLUMNS))
        self.assertAlmostEqual(len(d["t_s"]) / 2000.0, 3.3, delta=0.01)
        ms = [m for m in analyze(d, 5.0, 10.0, "ref_rpm", "speed_rpm", 0.5) if abs(m["amp_deg"]) > 1]
        self.assertEqual([round(m["target_deg"]) for m in ms], [300, 600, 0])
        for m in ms:
            self.assertIsNotNone(m["settle_s"])
            self.assertLess(abs(m["ess_deg"]), 10.0)
            self.assertIn("ripple_std", m)
        self.assertGreater(max(d["theta_deg"]), 3000.0)      # motor sa naozaj otacal (poloha rozvinuta)

    def test_overspeed_stops_motor(self):
        res = run_sim([(600.0, 1.0)], settle_s=0.1, max_rpm=400.0)
        self.assertIn("prekrocena rychlost", res["fault"])
        self.assertLess(res["data"]["t_s"][-1], 1.0)


if __name__ == "__main__":
    unittest.main()
