#!/usr/bin/env python3
"""Drop -gki- inside the 6.1 module vermagic without cutting the C string.

The CEYB1 kernel expects
5.10.209-android12-9-29539912-abS901EXXSCEYB1 SMP preempt mod_unload modversions aarch64.
Padding the removed bytes with NULs in the middle terminates that string early
and insmod returns Exec format error.
"""
import os
import sys

OLD = b"android12-9-gki-29539912"
NEW = b"android12-9-29539912"


def patch(path):
    data = bytearray(open(path, "rb").read())
    mark = data.find(b"vermagic=")
    if mark < 0:
        return False
    end = data.find(b"\x00", mark)
    if end < 0 or data.find(OLD, mark, end) < 0:
        return False
    start = data.find(OLD, mark, end)
    pad = len(OLD) - len(NEW)
    tail = bytes(data[start + len(OLD):end])
    data[start:start + len(NEW)] = NEW
    data[start + len(NEW):end - pad] = tail
    data[end - pad:end] = b"\x00" * pad
    open(path, "wb").write(data)
    return True


def main():
    root = sys.argv[1]
    n = 0
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name.endswith(".ko") and patch(os.path.join(dirpath, name)):
                n += 1
    kgsl = None
    for dirpath, _, files in os.walk(root):
        if "msm_kgsl.ko" in files:
            kgsl = os.path.join(dirpath, "msm_kgsl.ko")
            break
    if kgsl is None:
        raise SystemExit("msm_kgsl.ko not in vendor_dlkm")
    blob = open(kgsl, "rb").read()
    i = blob.find(b"vermagic=")
    text = blob[i:i + 120]
    print(text)
    if b"-gki-" in text:
        raise SystemExit("vermagic still has -gki-")
    magic = text.split(b"\x00", 1)[0]
    if b"29539912-abS901EXXSCEYB1" not in magic:
        raise SystemExit(f"vermagic was cut: {magic}")
    print("patched", n)


if __name__ == "__main__":
    main()
