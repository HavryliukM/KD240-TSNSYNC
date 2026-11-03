import unittest

from kd240sync import config, motor as motor_mod, position_test


class PositionTestTests(unittest.TestCase):
    def _run(self, steps, **kw):
        cfg = config.load(None, {"receiver": {"mode": "voltage_pd"}})
        m = motor_mod.create(cfg)
        m.open()
        try:
            return position_test.run(cfg, m, steps, log=lambda *_: None, **kw)
        finally:
            m.close()

    def test_parse_steps(self):
        self.assertEqual(position_test.parse_steps("90:2, 0:1.5,45"), [(90.0, 2.0), (0.0, 1.5), (45.0, 2.0)])

    def test_reference_ramp_and_step(self):
        r = position_test.Reference([(10.0, 1.0)], 0.1, 0.0)
        while not r.done:
            r.update(0.001)
        self.assertEqual(r.value, 10.0)
        r = position_test.Reference([(10.0, 1.0)], 0.1, 20.0)
        for _ in range(500):
            r.update(0.001)
        self.assertAlmostEqual(r.value, 8.0, delta=0.1)     # 0.1 s drzanie + 0.4 s rampy pri 20 deg/s

    def test_step_response_in_simulation(self):
        res = self._run([(20.0, 1.5), (0.0, 1.0)], settle_s=0.3)
        self.assertEqual(res["fault"], "")
        d = res["data"]
        self.assertGreater(len(d["t_s"]), 1500)
        self.assertEqual(set(d), set(position_test.COLUMNS))
        self.assertAlmostEqual(d["ref_deg"][-1], 0.0)
        self.assertLess(abs(d["err_deg"][-1]), 3.0)         # po skoku sa ustali
        self.assertGreater(max(d["theta_deg"]), 15.0)       # motor sa skutocne pohol

    def test_overspeed_faults_and_stops(self):
        res = self._run([(180.0, 1.0)], settle_s=0.1, max_rpm=1.0)
        self.assertIn("rychlost", res["fault"])


if __name__ == "__main__":
    unittest.main()
