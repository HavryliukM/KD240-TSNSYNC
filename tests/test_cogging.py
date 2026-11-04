import math
import os
import tempfile
import unittest

from kd240sync import cogging, config, position_test
from kd240sync.motor.sim import SimMotor
from tests.test_position_test import VirtualLoop


def ramp_in_sim(cog_v, table_path="", kfc=0.0):
    over = {"receiver": {"mode": "voltage_pd",
                         "voltage_pd": {"kfc_v": kfc, "cogging_table": table_path}}}
    cfg = config.load(None, over)
    loop = VirtualLoop()
    m = SimMotor(**cfg.motor.sim, clock=loop.clock, cog_v=cog_v, initial_theta_deg=37.0)
    m.open()
    try:
        res = position_test.run(cfg, m, [(360.0, 9.0), (0.0, 9.0)], ramp_dps=45.0, settle_s=0.3,
                                log=lambda *_: None, loop=loop)
    finally:
        m.close()
    return res


def moving_rms(d):
    ref, e = d["ref_deg"], d["err_deg"]
    mv = [e[i] for i in range(1, len(ref)) if ref[i] != ref[i - 1]]
    return math.sqrt(sum(x * x for x in mv) / len(mv))


class CoggingTests(unittest.TestCase):
    def test_lookup_interpolates_and_wraps(self):
        t = cogging.CoggingTable([0.0, 1.0, 0.0, -1.0])          # biny po 90 deg
        self.assertAlmostEqual(t(45.0), 0.5)
        self.assertAlmostEqual(t(90.0), 1.0)
        self.assertAlmostEqual(t(315.0), -0.5)                    # medzi 270 a 360 = 0
        self.assertAlmostEqual(t(360.0 + 90.0), 1.0)
        self.assertAlmostEqual(cogging.CoggingTable([1.0, 1.0], gain=0.5)(10.0), 0.5)

    def test_build_recovers_cogging_and_friction(self):
        # synteticka rampa: u = trenie v smere pohybu + cogging(uhol)
        ref, raw, u = [], [], []
        for k in range(2 * 3600):
            up = k < 3600
            a = (k if up else 7200 - k) * 0.1
            ref.append(a)
            raw.append((a + 200.0) % 360.0)
            u.append((0.12 if up else -0.12) + 0.15 * math.sin(math.radians(12 * raw[-1])))
        t, fric, cover = cogging.build({"ref_deg": ref, "u": u, "raw_deg": raw}, smooth=1)
        self.assertAlmostEqual(fric, 0.12, delta=0.01)
        self.assertEqual(cover, 1.0)
        for ang in (7.5, 22.5, 100.0):
            self.assertAlmostEqual(t(ang), 0.15 * math.sin(math.radians(12 * ang)), delta=0.02)

    def test_save_load_roundtrip_and_limit(self):
        t = cogging.CoggingTable([0.0, 0.4, -0.4, 0.1])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cog.csv")
            t.save(p)
            back = cogging.load(p, limit=0.3)
        self.assertEqual(back.values, [0.0, 0.3, -0.3, 0.1])

    def test_table_from_ramp_reduces_error_in_simulation(self):
        # cely retazec ako na doske: rampa bez kompenzacie -> tabulka z raw_deg -> rampa s tabulkou
        base = ramp_in_sim(0.15)
        self.assertEqual(base["fault"], "")
        table, fric, cover = cogging.build(base["data"])
        self.assertGreater(cover, 0.95)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cog.csv")
            table.save(p)
            comp = ramp_in_sim(0.15, p)
        self.assertEqual(comp["fault"], "")
        self.assertLess(moving_rms(comp["data"]), 0.5 * moving_rms(base["data"]))


if __name__ == "__main__":
    unittest.main()
