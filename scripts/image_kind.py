#!/usr/bin/env python3
import struct
import sys

path = sys.argv[1]
with open(path, "rb") as f:
    head = f.read(2048)
if head[:4] == b"\x3a\xff\x26\xed":
    print("sparse")
elif len(head) > 1028 and struct.unpack_from("<I", head, 1024)[0] == 0xE0F5E1E2:
    print("erofs")
elif len(head) > 1028 and struct.unpack_from("<I", head, 1024)[0] == 0xF2F52010:
    print("f2fs")
elif len(head) > 0x43A and struct.unpack_from("<H", head, 0x438)[0] == 0xEF53:
    print("ext4")
else:
    print("unknown")
