#!/usr/bin/env python3
"""Synthetic LP image: old offset misses, fixed offset finds the header."""
import os
import struct
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import lpunpack

GEOM_MAGIC = 0x616C4467
HDR_MAGIC = 0x414C5030
RESERVED = 4096
GEOM_SIZE = 4096


def main():
    max_size = 65536
    slots = 2
    header_size = 256
    blob = bytearray(max_size)
    struct.pack_into("<IHH I", blob, 0, HDR_MAGIC, 10, 2, header_size)
    struct.pack_into("<I", blob, 44, 0)
    off = 80
    for entry_size in (52, 24, 48, 64):
        struct.pack_into("<III", blob, off, 0, 0, entry_size)
        off += 12

    with tempfile.TemporaryDirectory() as tmp:
        image = os.path.join(tmp, "super.img")
        size = RESERVED + GEOM_SIZE * 2 + slots * max_size * 2 + 4096
        with open(image, "wb") as f:
            f.truncate(size)
            geom = bytearray(GEOM_SIZE)
            struct.pack_into("<II", geom, 0, GEOM_MAGIC, 52)
            struct.pack_into("<III", geom, 40, max_size, slots, 4096)
            f.seek(RESERVED)
            f.write(geom)
            f.seek(RESERVED + GEOM_SIZE)
            f.write(geom)
            # Place a decoy at the OLD incorrect base so a regression fails loudly.
            f.seek(RESERVED + GEOM_SIZE)
            f.write(b"\x00" * 4)
            f.seek(RESERVED + GEOM_SIZE)
            f.write(geom)
            f.seek(RESERVED + GEOM_SIZE * 2)
            f.write(blob)
        out = os.path.join(tmp, "parts")
        lpunpack.unpack(image, out, [])
        # Confirm old offset would miss.
        with open(image, "rb") as f:
            f.seek(RESERVED + GEOM_SIZE)
            old = struct.unpack("<I", f.read(4))[0]
            f.seek(RESERVED + GEOM_SIZE * 2)
            fixed = struct.unpack("<I", f.read(4))[0]
        assert old == GEOM_MAGIC, hex(old)
        assert fixed == HDR_MAGIC, hex(fixed)
        print("synthetic_ok")


if __name__ == "__main__":
    main()
