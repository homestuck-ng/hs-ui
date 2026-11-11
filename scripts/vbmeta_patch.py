#!/usr/bin/env python3
"""Set AVB flags to 0x3, big-endian, and pad to 4096 bytes."""
import sys

src, dest = sys.argv[1], sys.argv[2]
blob = bytearray(open(src, "rb").read())
if blob[:4] != b"AVB0":
    raise SystemExit("not vbmeta: " + src)
blob[0x78:0x7C] = b"\x00\x00\x00\x03"
if len(blob) % 4096:
    blob += b"\x00" * (4096 - (len(blob) % 4096))
open(dest, "wb").write(blob)
print(dest, len(blob), blob[0x78:0x7C].hex())
