import unittest

from kd240sync import config, position_test
from kd240sync.motor.sim import SimMotor


class VirtualLoop:
    """Virtualny cas pre slucku aj simulovany motor: deterministicke a bez cakania (Windows ma vypadky 100 ms)."""

    def __init__(self, period_s=0.001):
        self.now = 0
        self.period = int(period_s * 1e9)

    def clock(self):
        return self.now

    def wait(self):
        self.now += self.period
        return self.now

    def stats(self):
        return {"cycles": self.now // self.period, "overruns": 0, "mean_jitter_us": 0.0, "max_jitter_us": 0.0}


def run_sim(steps, kfc=None, **kw):
    over = {"receiver": {"mode": "voltage_pd"}}
    if kfc is not None:
        over["receiver"]["voltage_pd"] = {"kfc_v": kfc}
    cfg = config.load(None, over)
    loop = VirtualLoop()
    m = SimMotor(**cfg.motor.sim, clock=loop.clock)
    m.open()
    try:
        return position_test.run(cfg, m, steps, log=lambda *_: None, loop=loop, **kw)
    finally:
        m.close()


class PositionTestTests(unittest.TestCase):
    def _run(self, steps, **kw):
        return run_sim(steps, **kw)

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

    def test_friction_feedforward_term(self):
        from kd240sync.controller import TorquePD
        c = TorquePD(0.0, 0.0, kfc=0.13, fc_w0_dps=10.0, limit_a=1.0, slew_a_s=1e6)
        self.assertAlmostEqual(c.update(0.0, 0.0, 0.005, 45.0), 0.13)
        c.reset()
        self.assertAlmostEqual(c.update(0.0, 0.0, 0.005, -5.0), -0.065)      # linearne pod fc_w0
        c.reset()
        self.assertEqual(c.update(0.0, 0.0, 0.005, 0.0), 0.0)

    def test_friction_compensation_improves_ramp_in_simulation(self):
        def rms(kfc):
            res = run_sim([(90.0, 2.5)], kfc=kfc, ramp_dps=45.0, settle_s=0.2)
            self.assertEqual(res["fault"], "")
            d = res["data"]
            moving = [e for e, t in zip(d["err_deg"], d["t_s"]) if 0.5 < t < 2.2]
            return (sum(e * e for e in moving) / len(moving)) ** 0.5
        # kfc = mrtve pasmo simulovaneho motora (0.09 V) ho takmer presne vyrusi; prekompenzacia uz menej
        base = rms(0.0)
        self.assertLess(rms(0.09), 0.3 * base)
        self.assertLess(rms(0.13), base)

    def test_raw_angle_is_recorded(self):
        res = self._run([(30.0, 0.5)], settle_s=0.1)
        raw = res["data"]["raw_deg"]
        self.assertTrue(all(0.0 <= x < 360.0 for x in raw))

    def test_overspeed_faults_and_stops(self):
        res = self._run([(180.0, 1.0)], settle_s=0.1, max_rpm=1.0)
        self.assertIn("rychlost", res["fault"])


if __name__ == "__main__":
    unittest.main()
