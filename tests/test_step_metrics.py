import math
import unittest

from kd240sync import step_metrics


def second_order(t, amp, zeta=0.5, wn=30.0):
    wd = wn * math.sqrt(1 - zeta * zeta)
    phi = math.acos(zeta)
    return amp * (1 - math.exp(-zeta * wn * t) * math.sin(wd * t + phi) / math.sqrt(1 - zeta * zeta))


class StepMetricsTests(unittest.TestCase):
    def _data(self):
        t = [i * 0.001 for i in range(3000)]
        ref = [0.0 if x < 0.5 else 20.0 for x in t]
        theta = [0.0 if x < 0.5 else second_order(x - 0.5, 20.0) for x in t]
        return t, ref, theta

    def test_segments_split_on_reference_change(self):
        t, ref, _ = self._data()
        self.assertEqual(step_metrics.segments(t, ref), [(500, 3000)])
        # rampa je jeden usek, nie tisic
        ramp = [min(10.0, max(0.0, (x - 0.5) * 20.0)) for x in t]
        self.assertEqual(len(step_metrics.segments(t, ramp)), 1)

    def test_second_order_overshoot_matches_theory(self):
        t, ref, theta = self._data()
        m = step_metrics.analyze({"t_s": t, "ref_deg": ref, "theta_deg": theta})[0]
        mp_theory = 100.0 * math.exp(-math.pi * 0.5 / math.sqrt(1 - 0.25))    # 16.3 %
        self.assertAlmostEqual(m["overshoot_pct"], mp_theory, delta=0.5)
        self.assertAlmostEqual(m["amp_deg"], 20.0)
        self.assertIsNotNone(m["settle_s"])
        self.assertLess(abs(m["ess_deg"]), 0.05)
        self.assertGreater(m["rise_s"], 0.0)

    def test_not_settled_and_steady_state_error(self):
        t, ref, _ = self._data()
        theta = [0.0 if x < 0.5 else 15.0 for x in t]        # zasekne sa 5 deg pred cielom
        m = step_metrics.analyze({"t_s": t, "ref_deg": ref, "theta_deg": theta})[0]
        self.assertIsNone(m["settle_s"])
        self.assertAlmostEqual(m["ess_deg"], -5.0)
        self.assertEqual(m["overshoot_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
