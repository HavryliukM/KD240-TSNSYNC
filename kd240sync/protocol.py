"""Format UDP paketu, ktory posiela doska 1 (sender) doske 2 (receiver).

Little-endian, bez zarovnania (28 bajtov):
  H  magic      0x4B54
  B  version    1
  B  flags      bit0 = VALID, bit1 = STOP (sender konci, receiver ma motor uvolnit)
  I  seq        poradove cislo paketu (kazdy paket +1)
  Q  t_tx_ns    cas odoslania, CLOCK_REALTIME v nanosekundach
  d  theta_deg  rozvinuty (viacotackovy) uhol motora 1 v stupnoch
  f  omega_rpm  namerane otacky motora 1
"""
import struct
from dataclasses import dataclass

MAGIC = 0x4B54
VERSION = 1
FMT = "<HBBIQdf"
SIZE = struct.calcsize(FMT)

FLAG_VALID = 0x01
FLAG_STOP = 0x02


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Packet:
    seq: int
    t_tx_ns: int
    theta_deg: float
    omega_rpm: float
    flags: int = FLAG_VALID

    @property
    def stop(self) -> bool:
        return bool(self.flags & FLAG_STOP)


def pack(p: Packet) -> bytes:
    return struct.pack(FMT, MAGIC, VERSION, p.flags, p.seq & 0xFFFFFFFF,
                       p.t_tx_ns, p.theta_deg, p.omega_rpm)


def unpack(data: bytes) -> Packet:
    if len(data) != SIZE:
        raise ProtocolError(f"zla dlzka {len(data)} (ocakavane {SIZE})")
    magic, ver, flags, seq, t_tx, theta, omega = struct.unpack(FMT, data)
    if magic != MAGIC:
        raise ProtocolError("zly magic")
    if ver != VERSION:
        raise ProtocolError(f"nepodporovana verzia {ver}")
    return Packet(seq=seq, t_tx_ns=t_tx, theta_deg=theta, omega_rpm=omega, flags=flags)
