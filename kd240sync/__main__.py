"""Spustenie: python3 -m kd240sync {sender|receiver|demo} [--config subor.toml]"""
import argparse
import queue
import signal
import threading

from . import config, motor as motor_mod, net


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kd240sync")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sender", "receiver"):
        p = sub.add_parser(name)
        p.add_argument("--config", "-c", default=None)
        p.add_argument("--rt", action="store_true", help="skus SCHED_FIFO (root)")
    sub.choices["sender"].add_argument("--rpm", type=float, default=None,
                                       help="pociatocna rychlost [rpm]")
    d = sub.add_parser("demo")
    d.add_argument("--seconds", type=float, default=12.0)
    args = ap.parse_args(argv)

    if args.cmd == "demo":
        from . import demo
        s = demo.run_demo(duration_s=args.seconds, quiet=False)
        print("sender:  ", s["sender"])
        print("receiver:", s["receiver"])
        return 0

    cfg = config.load(args.config)
    if args.cmd == "sender" and args.rpm is not None:
        cfg["sender"]["initial_rpm"] = args.rpm
    if args.rt:
        from .timing import try_realtime
        print("realtime:", "ok" if try_realtime() else "nepodarilo sa (potrebny root)")

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    if hasattr(signal, "SIGHUP"):       # pad SSH spojenia nesmie nechat motor bezat
        signal.signal(signal.SIGHUP, lambda *_: stop.set())
    motor = motor_mod.create(cfg)

    if args.cmd == "sender":
        from . import sender
        sock = net.make_sender_socket(cfg)
        cmds = queue.SimpleQueue()
        threading.Thread(target=sender.stdin_commands, args=(cmds, stop), daemon=True).start()
        print("sender: prikazy 'rpm <cislo>', 'stop', 'quit'; Ctrl+C ukonci")
        stats = sender.run(cfg, motor, sock, stop, commands=cmds)
    else:
        from . import receiver
        sock = net.make_receiver_socket(cfg)
        print("receiver: caka na pakety; Ctrl+C ukonci")
        stats = receiver.run(cfg, motor, sock, stop)
    print("statistiky:", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
