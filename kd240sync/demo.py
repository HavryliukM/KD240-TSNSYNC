"""Simulacia sender -> receiver na jednom pocitaci (bez dosky a bez motora)."""
import socket
import threading
import time

from . import config, motor as motor_mod, net, receiver, sender


def run_demo(duration_s=12.0, schedule=None, overrides=None, quiet=True):
    """Spusti sender a receiver s simulovanymi motormi cez localhost.

    schedule: zoznam (cas_s, rpm) pre sender. Vrati statistiky oboch stran.
    """
    schedule = schedule or [(0.0, 300.0), (4.0, -200.0), (7.0, 0.0)]
    base = {"network": {"bind_ip": "127.0.0.1", "peer_ip": "127.0.0.1", "port": 0},
            "motor": {"backend": "sim"}}
    cfg = config.load(None, _merge(base, overrides or {}))
    rsock = net.make_receiver_socket(cfg)
    cfg["network"]["port"] = rsock.getsockname()[1]
    ssock = net.make_sender_socket(cfg)
    m_tx = motor_mod.create(cfg)
    m_rx = motor_mod.create(cfg)
    stop = threading.Event()
    stats = {}
    import queue
    cmds = queue.SimpleQueue()

    t_rx = threading.Thread(target=lambda: stats.__setitem__(
        "receiver", receiver.run(cfg, m_rx, rsock, stop, quiet=quiet)))
    t_tx = threading.Thread(target=lambda: stats.__setitem__(
        "sender", sender.run(cfg, m_tx, ssock, stop, commands=cmds, quiet=quiet)))
    t_rx.start()
    t_tx.start()
    t0 = time.monotonic()
    pending = sorted(schedule)
    while time.monotonic() - t0 < duration_s:
        while pending and time.monotonic() - t0 >= pending[0][0]:
            cmds.put(("rpm", pending.pop(0)[1]))
        time.sleep(0.01)
    stop.set()
    t_tx.join()
    t_rx.join()
    rsock.close()
    ssock.close()
    stats["final_error_deg"] = None
    return stats


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out
