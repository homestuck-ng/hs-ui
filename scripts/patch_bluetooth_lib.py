#!/usr/bin/env python3
"""Patch Samsung's bluetooth library the way the TWRP zip does.

One UI 5.1 keeps libbluetooth_jni.so inside the signed
com.android.btservices.apex. Rewriting that apex breaks the APK v3
content digest and PackageManager kills system_server. The TWRP
installer leaves the apex alone, extracts the library, and writes the
patched copy to system/lib64.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

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


def label(path):
    os.chown(path, 0, 0)
    os.chmod(path, 0o644)
    os.setxattr(path, "security.selinux", b"u:object_r:system_lib_file:s0\0")


def read_payload_lib(payload):
    mnt = tempfile.mkdtemp(prefix="btmnt-")
    subprocess.check_call(["sudo", "mount", "-o", "loop,ro", payload, mnt])
    try:
        return subprocess.check_output(
            ["sudo", "cat", os.path.join(mnt, "lib64", "libbluetooth_jni.so")]
        )
    finally:
        subprocess.check_call(["sudo", "umount", mnt])
        os.rmdir(mnt)


def install_from_apex(apex_path):
    """Write a patched system/lib64 copy. The apex file is not modified."""
    system_dir = os.path.dirname(os.path.dirname(apex_path))
    dest = os.path.join(system_dir, "lib64", "libbluetooth_jni.so")
    tmp = tempfile.mkdtemp(prefix="btapex-")
    payload = os.path.join(tmp, "apex_payload.img")
    try:
        with zipfile.ZipFile(apex_path) as archive:
            with archive.open("apex_payload.img") as src, open(payload, "wb") as out:
                shutil.copyfileobj(src, out)
        data = read_payload_lib(payload)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    updated, status = patch_bytes(data)
    if updated is None:
        print(status, apex_path)
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as out:
        out.write(updated)
    subprocess.check_call(["sudo", sys.executable, __file__, "--label", dest])
    print(status, dest, "apex left signed", apex_path)
    return True


def main():
    root = sys.argv[1]
    hits = 0
    written = set()
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name == "com.android.btservices.apex":
                dest = install_from_apex(os.path.join(dirpath, name))
                if dest:
                    hits += 1
                    written.add(os.path.realpath(os.path.join(
                        os.path.dirname(dirpath), "lib64", "libbluetooth_jni.so"
                    )))
    for dirpath, _, files in os.walk(root):
        for name in files:
            if name not in {"libbluetooth.so", "libbluetooth_jni.so", "bluetooth.default.so"}:
                continue
            path = os.path.realpath(os.path.join(dirpath, name))
            if path in written:
                continue
            if patch_file(path):
                hits += 1
    if hits == 0:
        print("bluetooth library pattern was not found")
        return 1
    print("bluetooth library patched", hits)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--label":
        label(sys.argv[2])
        raise SystemExit(0)
    sys.exit(main())
