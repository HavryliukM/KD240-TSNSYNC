"""Pomocne funkcie pre UDP sockety."""
import socket


def _apply_priority(sock, cfg):
    prio = int(cfg.network.so_priority)
    if prio >= 0 and hasattr(socket, "SO_PRIORITY"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_PRIORITY, prio)


def make_sender_socket(cfg) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((cfg.network.bind_ip, 0))     # fixuje odchadzajuce rozhranie
    _apply_priority(s, cfg)
    return s


def make_receiver_socket(cfg, timeout_s=0.05) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((cfg.network.bind_ip, int(cfg.network.port)))
    s.settimeout(timeout_s)
    return s
