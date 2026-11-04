import unittest

from kd240sync import config, speed_test
from kd240sync.controller import SpeedPI
from kd240sync.motor.sim import SimMotor
from kd240sync.step_metrics import analyze
from tests.test_position_test import VirtualLoop


def run_sim(steps, mode="voltage", **kw):
    cfg = config.load(None)
    loop = VirtualLoop(0.0005)
    m = SimMotor(**cfg.motor.sim, clock=loop.clock)
    m.open()
    try:
        return speed_test.run(cfg, m, steps, sample_hz=2000.0, mode=mode, log=lambda *_: None, loop=loop, **kw)
    finally:
        m.close()


def step_ms(d):
    return [m for m in analyze(d, 5.0, 10.0, "ref_rpm", "speed_f", 0.5) if abs(m["amp_deg"]) > 1]


class SpeedPITests(unittest.TestCase):
    def test_feedforward_friction_and_integrator(self):
        c = SpeedPI(kp=0.0, ki=0.0, kff=0.002, kfc=0.1, fc_w0_rpm=20.0, limit_v=1.5, slew_v_s=1e6)
        self.assertAlmostEqual(c.update(300.0, 300.0, 0.001), 0.7)          # 0.6 V kff + 0.1 V trenie
        c = SpeedPI(kp=0.0, ki=10.0, limit_v=0.5, slew_v_s=1e6, i_limit_v=0.3)
        for _ in range(1000):
            u = c.update(100.0, 0.0, 0.001)
        self.assertAlmostEqual(u, 0.3)                                      # integrator obmedzeny i_limit
        c = SpeedPI(kp=0.0, ki=10.0, limit_v=1.5, slew_v_s=1e6, i_band_rpm=30.0)
        for _ in range(100):
            c.update(200.0, 0.0, 0.001)                                     # velka chyba pri nabehu
        self.assertEqual(c.integ, 0.0)
        c.update(200.0, 190.0, 0.001)
        self.assertAlmostEqual(c.integ, 0.1)                                # pri malej chybe integruje


class SpeedTestTests(unittest.TestCase):
    def test_voltage_pi_reaches_targets(self):
        res = run_sim([(200.0, 1.5), (400.0, 1.5), (0.0, 1.5)], settle_s=0.3)
        self.assertEqual(res["fault"], "")
        d = res["data"]
        self.assertEqual(set(d), set(speed_test.COLUMNS))
        ms = step_ms(d)
        self.assertEqual([round(m["target_deg"]) for m in ms], [200, 400, 0])
        for m in ms:
            self.assertIsNotNone(m["settle_s"])
            self.assertLess(abs(m["ess_deg"]), 5.0)
            self.assertLess(m["rise_s"], 0.15)
            self.assertLess(m["overshoot_pct"], 8.0)                        # podmienena integracia
        self.assertGreater(max(d["u"]), 0.5)                                # regulator naozaj daval napatie

    def test_library_mode_still_available(self):
        res = run_sim([(300.0, 1.0), (0.0, 1.0)], mode="library", settle_s=0.3)
        self.assertEqual(res["fault"], "")
        self.assertTrue(all(u != u for u in res["data"]["u"]))             # bez vlastneho regulatora u = NaN
        self.assertGreater(max(res["data"]["speed_rpm"]), 250.0)

    def test_overspeed_stops_motor(self):
        res = run_sim([(600.0, 1.0)], settle_s=0.1, max_rpm=400.0)
        self.assertIn("prekrocena rychlost", res["fault"])
        self.assertLess(res["data"]["t_s"][-1], 1.0)


class SenderVoltageModeTests(unittest.TestCase):
    def test_sender_voltage_pi_drives_receiver(self):
        from kd240sync.demo import run_demo
        s = run_demo(duration_s=6.0, overrides={"sender": {"mode": "voltage_pi"},
                                                "receiver": {"mode": "voltage_pd"}})
        self.assertEqual(s["sender"]["fault"], "")
        self.assertEqual(s["receiver"]["fault"], "")
        self.assertLess(s["receiver"]["err_rms_deg"], 8.0)

    def test_board_configs_use_voltage_pi_sender(self):
        import os
        base = os.path.join(os.path.dirname(__file__), "..", "config")
        for name in ("board1.toml", "board1_loopback.toml"):
            cfg = config.load(os.path.join(base, name))
            self.assertEqual(cfg.sender.mode, "voltage_pi", name)
            self.assertLessEqual(cfg.sender.max_rpm, 600, name)    # pod stropom napatia 1,5 V

if __name__ == "__main__":
    unittest.main()
