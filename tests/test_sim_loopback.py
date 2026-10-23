import socket
import threading
import time
import unittest

from kd240sync import config, motor as motor_mod, net, protocol, receiver
from kd240sync.demo import run_demo


class LoopbackTests(unittest.TestCase):
    def test_tracking_in_simulation(self):
        s = run_demo(duration_s=8.0)
        r = s["receiver"]
        self.assertEqual(r["fault"], "")
        self.assertEqual(r["state"], "RUN")
        self.assertEqual(r["bad"], 0)
        self.assertLess(r["lost"], 5)
        self.assertLess(r["err_rms_deg"], 6.0)

    def test_opposite_direction(self):
        s = run_demo(duration_s=6.0, overrides={"receiver": {"direction": -1}})
        r = s["receiver"]
        self.assertEqual(r["fault"], "")
        self.assertLess(r["err_rms_deg"], 6.0)

    def _start_receiver(self, overrides=None):
        cfg = config.load(None, {"network": {"port": 0}, **(overrides or {})})
        rsock = net.make_receiver_socket(cfg)
        port = rsock.getsockname()[1]
        m = motor_mod.create(cfg)
        stop = threading.Event()
        out = {}
        t = threading.Thread(target=lambda: out.update(receiver.run(cfg, m, rsock, stop, quiet=True)))
        t.start()
        return cfg, port, m, stop, t, out

    def _send(self, tx, port, seq, theta, omega=0.0, flags=protocol.FLAG_VALID):
        p = protocol.Packet(seq, time.time_ns(), theta, omega, flags)
        tx.sendto(protocol.pack(p), ("127.0.0.1", port))

    def test_watchdog_releases_motor(self):
        cfg, port, m, stop, t, out = self._start_receiver()
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i in range(60):
            self._send(tx, port, i, 10.0)
            time.sleep(0.005)
        self.assertEqual(m.mode, "torque")      # reguluje
        time.sleep(0.3)                         # pakety neprichadzaju
        self.assertEqual(m.mode, "off")         # watchdog uvolnil motor
        stop.set()
        t.join()

    def test_fault_on_large_error(self):
        cfg, port, m, stop, t, out = self._start_receiver()
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i in range(20):
            self._send(tx, port, i, 0.0)
            time.sleep(0.005)
        for i in range(20, 40):
            self._send(tx, port, i, 500.0)      # skok o 500 deg -> chyba nad limit
            time.sleep(0.005)
        time.sleep(0.1)
        self.assertEqual(m.mode, "off")
        stop.set()
        t.join()
        self.assertEqual(out["state"], "FAULT")

    def test_stop_flag_releases_motor(self):
        cfg, port, m, stop, t, out = self._start_receiver()
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for i in range(30):
            self._send(tx, port, i, 5.0)
            time.sleep(0.005)
        self.assertEqual(m.mode, "torque")
        self._send(tx, port, 30, 0.0, flags=protocol.FLAG_STOP)
        time.sleep(0.1)
        self.assertEqual(m.mode, "off")
        stop.set()
        t.join()


if __name__ == "__main__":
    unittest.main()
