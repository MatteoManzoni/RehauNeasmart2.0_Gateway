import struct


def pack_dpt9001(f):
    buffer = bytearray([0, 0])

    if f > 670760.96:
        f = 670760.96
    elif f < -671088.64:
        f = -671088.64

    signed_mantissa = int(f * 100)
    exp = 0

    while signed_mantissa > 2047 or signed_mantissa < -2048:
        signed_mantissa //= 2
        exp += 1

    buffer[0] |= (exp & 15) << 3

    if signed_mantissa < 0:
        signed_mantissa += 2048
        buffer[0] |= 1 << 7

    mantissa = signed_mantissa

    buffer[0] |= (mantissa >> 8) & 7
    buffer[1] |= mantissa

    return struct.unpack('>H', buffer)[0]


def unpack_dpt9001(i):
    h = (i >> 8) & 0xFF
    l = i & 0xFF

    m = (int(h) & 7) << 8 | int(l)
    if (h & 0x80) == 0x80:
        m -= 2048

    e = (h >> 3) & 15

    f = 0.01 * float(m) * float(1 << e)

    return round(f, 2)
