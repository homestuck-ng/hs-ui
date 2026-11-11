#!/usr/bin/env python3
"""Strip -gki- from the 6.1 module vermagic so it matches the CEYB1 kernel."""
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
    repl = NEW + b"\x00" * (len(OLD) - len(NEW))
    data[start:start + len(OLD)] = repl
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
    print("patched", n)


if __name__ == "__main__":
    main()
