#!/usr/bin/env python3
"""Patch Samsung's bluetooth library the way BluetoothLibraryPatcher does.

The byte sequences are the arm64 patterns from 3arthur6's module. One UI 5.1
is API 33, so that pattern is tried first. The replacement is the same length.
"""
import os
import re
import struct
import sys
import zipfile
import zlib

# (api, pre, post) for the default arm64 path, then the qcom API 28-30 path.
PATTERNS = [
    (33, "6804003528008052", "2a00001428008052"),
    (34, "6804003528008052", "2b00001428008052"),
    (35, "480500352800805228", "530100142800805228"),
    (36, "00122a0140395f01086b00020054", "00122a0140395f01086bde030014"),
    (32, "........f9031f2af3031f2a41", "1f2003d5f9031f2af3031f2a48"),
    (31, "........f9031f2af3031f2a41", "1f2003d5f9031f2af3031f2a48"),
    (30, "........f3031f2af4031f2a3e", "1f2003d5f3031f2af4031f2a3e"),
    (29, "........f4031f2af3031f2ae8030032", "1f2003d5f4031f2af3031f2ae8031f2a"),
    (28, "88000034e8030032", "1f2003d5e8031f2a"),
    (27, "88000034e8030032", "1f2003d5e8031f2a"),
    (26, "88000034e8030032", "1f2003d5e8031f2a"),
    (30, "88000054691180522925c81a69000037", "1f2003d5691180522925c81a1f2003d5"),
    (29, "88000054691180522925c81a69000037", "1f2003d5691180522925c81a1f2003d5"),
    (28, "7f1d0071e91700f9e83c0054", "7f1d0071e91700f9e7010014"),
]


def hex_of(data):
    return data.hex()


def patch_bytes(data):
    blob = data.hex()
    for api, pre, post in PATTERNS:
        if len(pre) != len(post) or len(pre) % 2:
            continue
        updated = None
        for match in re.finditer(pre, blob):
            if match.start() % 2:
                continue
            start = match.start() // 2
            end = match.end() // 2
            updated = data[:start] + bytes.fromhex(post) + data[end:]
            break
        if updated is not None:
            return updated, "patched:" + str(api)
        if post in blob:
            return data, "already:" + str(api)
    return None, "no-match"


def patch_file(path):
    data = open(path, "rb").read()
    updated, status = patch_bytes(data)
    if updated is None:
        print(status, path)
        return False
    if status.startswith("patched"):
        open(path, "wb").write(updated)
    print(status, path)
    return True


def patch_stored_zip(path):
    with zipfile.ZipFile(path, "r") as archive:
        names = [info.filename for info in archive.infolist() if info.filename.endswith("libbluetooth_jni.so") or info.filename.endswith("apex_payload.img")]
    if not names:
        return False
    changed = False
    raw = bytearray(open(path, "rb").read())
    with zipfile.ZipFile(path, "r") as archive:
        for info in archive.infolist():
            if info.filename not in names or info.compress_type != zipfile.ZIP_STORED:
                continue
            data = archive.read(info.filename)
            updated, status = patch_bytes(data)
            print(status, path, info.filename)
            if not status.startswith("patched"):
                continue
            start = info.header_offset + 30 + len(info.filename) + len(info.extra)
            raw[start:start + len(updated)] = updated
            crc = zlib.crc32(updated) & 0xFFFFFFFF
            struct.pack_into("<I", raw, info.header_offset + 14, crc)
            # Central directory CRC is updated by scanning the name.
            marker = info.filename.encode()
            cursor = 0
            while True:
                pos = raw.find(b"PK\x01\x02", cursor)
                if pos < 0:
                    break
                name_len = struct.unpack_from("<H", raw, pos + 28)[0]
                name = raw[pos + 46:pos + 46 + name_len]
                if name == marker:
                    struct.pack_into("<I", raw, pos + 16, crc)
                    break
                cursor = pos + 4
            changed = True
    if changed:
        open(path, "wb").write(raw)
    return changed


def main():
    root = sys.argv[1]
    hits = 0
    for dirpath, _, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            if name in {"libbluetooth.so", "libbluetooth_jni.so", "bluetooth.default.so"}:
                if patch_file(path):
                    hits += 1
            elif name.startswith("com.android.bt") and name.endswith(".apex"):
                if patch_stored_zip(path):
                    hits += 1
    if hits == 0:
        print("bluetooth library pattern was not found")
        return 1
    print("bluetooth library patched", hits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
