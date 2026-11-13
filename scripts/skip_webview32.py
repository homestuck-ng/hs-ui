#!/usr/bin/env python3
"""Skip the 32-bit WebView relro at boot.

One UI 5.1 starts both WebView loaders. Every app on this hybrid is
arm64, so the 32-bit loader has nothing to serve. The arm64 loader stays.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import zipfile

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from smali_tools import assemble, disassemble, tool_paths

ABI32 = re.compile(
    r"(SUPPORTED_32_BIT_ABIS:\[Ljava/lang/String;\s+"
    r"array-length\s+(\w+),\s+\2\s+)"
    r"(if-lez\s+\2,\s+(:\w+)|goto\s+(:\w+))"
)


def rewrite_smali(text: str):
    start = text.find(".method private static blacklist createRelros(")
    if start < 0:
        start = text.find(".method private static createRelros(")
    if start < 0:
        return None
    end = text.find(".end method", start)
    if end < 0:
        return None
    end += len(".end method")
    body = text[start:end]
    if "SUPPORTED_64_BIT_ABIS" not in body or "createRelroFile" not in body:
        return None
    match = ABI32.search(body)
    if match is None:
        return None
    if match.group(3).startswith("goto"):
        return text
    label = match.group(4)
    updated = body[: match.start(3)] + "goto " + label + body[match.end(3) :]
    if not re.search(r"const/4 \w+, 0x1", updated):
        return None
    return text[:start] + updated + text[end:]


def patch_jar(jar_path: str, tool_dir: str) -> None:
    baksmali, smali = tool_paths(tool_dir)
    with zipfile.ZipFile(jar_path) as archive:
        dexes = [
            name
            for name in archive.namelist()
            if name.startswith("classes") and name.endswith(".dex")
        ]
    if not dexes:
        raise SystemExit("no dex in " + jar_path)
    changed = False
    touched = set()
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(jar_path) as archive:
            archive.extractall(tmp, dexes)
        for dex in dexes:
            dex_path = os.path.join(tmp, dex)
            if b"WebViewLibraryLoader" not in open(dex_path, "rb").read():
                continue
            smali_dir = os.path.join(tmp, dex + ".out")
            disassemble(baksmali, dex_path, smali_dir)
            target = None
            for dirpath, _, files in os.walk(smali_dir):
                if "WebViewLibraryLoader.smali" in files:
                    target = os.path.join(dirpath, "WebViewLibraryLoader.smali")
                    break
            if target is None:
                continue
            original = open(target, encoding="utf-8").read()
            updated = rewrite_smali(original)
            if updated is None:
                raise SystemExit("WebViewLibraryLoader createRelros was not recognized")
            if updated == original:
                print("32-bit WebView relro already skipped in", dex)
                return
            open(target, "w", encoding="utf-8", newline="\n").write(updated)
            assemble(smali, smali_dir, dex_path)
            changed = True
            touched.add(dex)
            print("patched", dex)
            break
        if not changed:
            raise SystemExit("WebViewLibraryLoader.smali was not found")
        tmp_jar = jar_path + ".tmp"
        with zipfile.ZipFile(jar_path, "r") as src, zipfile.ZipFile(tmp_jar, "w") as dst:
            for info in src.infolist():
                if info.filename in touched:
                    data = open(os.path.join(tmp, info.filename), "rb").read()
                else:
                    data = src.read(info.filename)
                dst.writestr(info, data)
        os.replace(tmp_jar, jar_path)


def main() -> None:
    root = sys.argv[1]
    jars = []
    for dirpath, _, files in os.walk(root):
        if "framework.jar" in files and "framework" in dirpath.replace("\\", "/").split("/"):
            jars.append(os.path.join(dirpath, "framework.jar"))
    if not jars:
        raise SystemExit("framework.jar not found under " + root)
    tool_dir = os.path.join(_SCRIPTS, "..", "prebuilts", "smali")
    patch_jar(jars[0], tool_dir)
    print("32-bit WebView relro skipped")


if __name__ == "__main__":
    main()
