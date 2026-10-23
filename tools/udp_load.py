#!/usr/bin/env python3
"""Generator pozadoveho UDP zatazenia (alebo prijimac, ktory pakety zahadzuje).

Odosielatel:  python3 tools/udp_load.py 111.222.0.20 --mbit 200 --seconds 30 --priority 1
Prijimac:     python3 tools/udp_load.py --sink --port 6000

--priority nastavi SO_PRIORITY. Na masteri sa priorita 0 mapuje na PCP 4 (ako riadiace
pakety), ina priorita ma byt best effort. Overit tcpdump-om (-e). [HYPOTEZA]
"""
import argparse
import socket
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest", nargs="?")
    ap.add_argument("--port", type=int, default=6000)
    ap.add_argument("--mbit", type=float, default=100.0)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--size", type=int, default=1400)
    ap.add_argument("--priority", type=int, default=-1)
    ap.add_argument("--sink", action="store_true")
    a = ap.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if a.sink:
        s.bind(("0.0.0.0", a.port))
        n = b = 0
        t0 = time.time()
        s.settimeout(1.0)
        print(f"sink na porte {a.port}, Ctrl+C ukonci")
        try:
            while True:
                try:
                    d, _ = s.recvfrom(65535)
                except socket.timeout:
                    continue
                n += 1
                b += len(d)
                if time.time() - t0 >= 1.0:
                    print(f"{n} paketov/s, {b * 8 / 1e6:.1f} Mbit/s")
                    n = b = 0
                    t0 = time.time()
        except KeyboardInterrupt:
            return 0
    if not a.dest:
        ap.error("zadaj cielovu adresu alebo --sink")
    if a.priority >= 0:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_PRIORITY, a.priority)
    payload = b"\x00" * a.size
    interval = a.size * 8 / (a.mbit * 1e6)
    t_end = time.monotonic() + a.seconds
    nxt = time.monotonic()
    sent = 0
    while time.monotonic() < t_end:
        s.sendto(payload, (a.dest, a.port))
        sent += 1
        nxt += interval
        d = nxt - time.monotonic()
        if d > 0:
            time.sleep(d)
    print(f"odoslanych paketov: {sent} (~{sent * a.size * 8 / a.seconds / 1e6:.1f} Mbit/s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
