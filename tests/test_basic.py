import unittest

from kd240sync import protocol
from kd240sync.angle import Unwrapper
from kd240sync.controller import TorquePD


class ProtocolTests(unittest.TestCase):
    def test_size(self):
        self.assertEqual(protocol.SIZE, 28)

    def test_roundtrip(self):
        p = protocol.Packet(seq=7, t_tx_ns=123456789, theta_deg=1234.5, omega_rpm=-300.25,
                            flags=protocol.FLAG_VALID)
        q = protocol.unpack(protocol.pack(p))
        self.assertEqual(q.seq, 7)
        self.assertEqual(q.t_tx_ns, 123456789)
        self.assertAlmostEqual(q.theta_deg, 1234.5)
        self.assertAlmostEqual(q.omega_rpm, -300.25, places=2)
        self.assertFalse(q.stop)

    def test_stop_flag(self):
        p = protocol.Packet(1, 1, 0.0, 0.0, protocol.FLAG_STOP)
        self.assertTrue(protocol.unpack(protocol.pack(p)).stop)

    def test_bad_input(self):
        good = protocol.pack(protocol.Packet(1, 1, 0.0, 0.0))
        with self.assertRaises(protocol.ProtocolError):
            protocol.unpack(good[:-1])
        with self.assertRaises(protocol.ProtocolError):
            protocol.unpack(b"\x00\x00" + good[2:])


class UnwrapTests(unittest.TestCase):
    def test_forward_and_backward(self):
        u = Unwrapper()
        vals = [350.0, 10.0, 30.0, 350.0, 330.0, 10.0]   # +20 +20 -40 -20 +40 (po prvej vzorke)
        out = [u.update(v) for v in vals]
        self.assertAlmostEqual(out[1] - out[0], 20.0)
        self.assertAlmostEqual(out[2] - out[1], 20.0)
        self.assertAlmostEqual(out[3] - out[2], -40.0)
        self.assertAlmostEqual(out[4] - out[3], -20.0)
        self.assertAlmostEqual(out[5] - out[4], 40.0)

    def test_many_turns(self):
        u = Unwrapper()
        total = 0.0
        raw = 0.0
        u.update(raw)
        for _ in range(1000):
            raw = (raw + 37.0) % 360.0
            total += 37.0
            self.assertAlmostEqual(u.update(raw), total, places=6)

    def test_multiturn_input_passes(self):
        # viacotackovy vstup s malymi krokmi sa nema menit
        u = Unwrapper()
        for v in range(300, 700, 20):
            self.assertAlmostEqual(u.update(float(v)), float(v))


class ControllerTests(unittest.TestCase):
    def test_limit_and_slew(self):
        c = TorquePD(kp=1.0, kd=0.0, limit_a=0.3, slew_a_s=10.0)
        out = c.update(100.0, 0.0, 0.01)       # velka chyba, ale slew 10 A/s * 10 ms = 0.1 A
        self.assertAlmostEqual(out, 0.1)
        for _ in range(100):
            out = c.update(100.0, 0.0, 0.01)
        self.assertAlmostEqual(out, 0.3)       # limit
        c.reset()
        self.assertEqual(c.out, 0.0)

    def test_sign(self):
        c = TorquePD(kp=0.01, kd=0.0, limit_a=1.0, slew_a_s=1e6)
        self.assertGreater(c.update(10.0, 0.0, 0.01), 0)
        c.reset()
        self.assertLess(c.update(-10.0, 0.0, 0.01), 0)


if __name__ == "__main__":
    unittest.main()
