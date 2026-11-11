#!/usr/bin/env python3
"""Shared baksmali/smali 3.x helpers for One UI 5.1 (API 33) dex."""
from __future__ import annotations

import os
import subprocess
import urllib.request

SMALI_VER = "3.0.10"
API_LEVEL = "33"
SMALI_URL = (
    f"https://github.com/baksmali/smali/releases/download/{SMALI_VER}/"
    f"smali-{SMALI_VER}-fat.jar"
)
BAKSMALI_URL = (
    f"https://github.com/baksmali/smali/releases/download/{SMALI_VER}/"
    f"baksmali-{SMALI_VER}-fat.jar"
)


def tool_paths(tool_dir: str) -> tuple[str, str]:
    os.makedirs(tool_dir, exist_ok=True)
    baksmali = os.path.join(tool_dir, f"baksmali-{SMALI_VER}-fat.jar")
    smali = os.path.join(tool_dir, f"smali-{SMALI_VER}-fat.jar")
    # Drop stale 2.5.x jars that previously poisoned this directory.
    for stale in ("baksmali.jar", "smali.jar"):
        path = os.path.join(tool_dir, stale)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    ensure_jar(BAKSMALI_URL, baksmali)
    ensure_jar(SMALI_URL, smali)
    return baksmali, smali


def ensure_jar(url: str, dest: str) -> str:
    if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
        return dest
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    tmp = dest + ".part"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dest)
    return dest


def run(args: list[str]) -> None:
    subprocess.check_call(args)


def disassemble(
    baksmali: str,
    dex_path: str,
    out: str,
    classes: list[str] | None = None,
) -> None:
    """Disassemble a dex. Optional classes are type descriptors without L/;."""
    base = ["java", "-jar", baksmali, "disassemble", "--api", API_LEVEL]
    if classes:
        # baksmali 3.x: --classes Lcom/foo/Bar;
        joined = ",".join(
            c if c.startswith("L") else f"L{c.replace('.', '/')};" for c in classes
        )
        base += ["--classes", joined]
    attempts = [
        base + [dex_path, "-o", out],
        ["java", "-jar", baksmali, "d", "-a", API_LEVEL, dex_path, "-o", out],
    ]
    last = attempts[0]
    for args in attempts:
        last = args
        try:
            run(args)
            return
        except subprocess.CalledProcessError:
            continue
    raise SystemExit(f"baksmali failed: {last}")


def assemble(smali: str, smali_dir: str, dex_path: str) -> None:
    attempts = [
        ["java", "-jar", smali, "assemble", "--api", API_LEVEL, smali_dir, "-o", dex_path],
        ["java", "-jar", smali, "a", "-a", API_LEVEL, smali_dir, "-o", dex_path],
    ]
    last = attempts[0]
    for args in attempts:
        last = args
        try:
            run(args)
            return
        except subprocess.CalledProcessError:
            continue
    raise SystemExit(f"smali failed: {last}")
