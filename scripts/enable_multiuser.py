#!/usr/bin/env python3
"""Enable Samsung multi-user the way UN1CA does.

Samsung phones force a single user unless the build looks like a tablet.
The framework helper is flipped so the user cap is 8 and the switcher is on.
"""
from __future__ import annotations

import os
import sys
import tempfile
import zipfile

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from smali_tools import assemble, disassemble, tool_paths

# One UI 5.1 marks the clinit with hidden-API "blacklist".
CLINIT = """.method static constructor blacklist <clinit>()V
    .registers 2

    const/4 v0, 0x1

    sput-boolean v0, Lcom/samsung/android/core/pm/multiuser/MultiUserSupportsHelper;->IS_TABLET:Z

    const/16 v1, 0x8

    sput v1, Lcom/samsung/android/core/pm/multiuser/MultiUserSupportsHelper;->DEFAULT_MAX_USERS:I

    sput-boolean v0, Lcom/samsung/android/core/pm/multiuser/MultiUserSupportsHelper;->DEFAULT_ENABLE_STATUS:Z

    return-void
.end method
"""


def rewrite_smali(text: str):
    start = -1
    for needle in (
        ".method static constructor blacklist <clinit>()V",
        ".method static constructor greylist <clinit>()V",
        ".method static constructor <clinit>()V",
    ):
        start = text.find(needle)
        if start >= 0:
            break
    if start < 0:
        return None
    end = text.find(".end method", start)
    if end < 0:
        return None
    end += len(".end method")
    body = text[start:end]
    if "DEFAULT_MAX_USERS" not in body or "IS_TABLET" not in body:
        return None
    if (
        "const/16 v1, 0x8" in body
        and "const/4 v0, 0x1" in body
        and "ro.build.characteristics" not in body
    ):
        return text
    return text[:start] + CLINIT.strip() + text[end:]


def dex_has_helper(dex_path: str) -> bool:
    return b"MultiUserSupportsHelper" in open(dex_path, "rb").read()


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
            if not dex_has_helper(dex_path):
                continue
            smali_dir = os.path.join(tmp, dex + ".out")
            disassemble(baksmali, dex_path, smali_dir)
            target = None
            for dirpath, _, files in os.walk(smali_dir):
                if "MultiUserSupportsHelper.smali" in files:
                    target = os.path.join(dirpath, "MultiUserSupportsHelper.smali")
                    break
            if target is None:
                continue
            original = open(target, encoding="utf-8").read()
            updated = rewrite_smali(original)
            if updated is None:
                raise SystemExit("MultiUserSupportsHelper clinit was not recognized")
            if updated == original:
                print("multi-user already enabled in", dex)
                return
            open(target, "w", encoding="utf-8", newline="\n").write(updated)
            assemble(smali, smali_dir, dex_path)
            changed = True
            touched.add(dex)
            print("patched", dex)
            break
        if not changed:
            raise SystemExit("MultiUserSupportsHelper.smali was not found")
        tmp_jar = jar_path + ".tmp"
        with zipfile.ZipFile(jar_path, "r") as src, zipfile.ZipFile(tmp_jar, "w") as dst:
            for info in src.infolist():
                if info.filename in touched:
                    data = open(os.path.join(tmp, info.filename), "rb").read()
                else:
                    data = src.read(info.filename)
                dst.writestr(info, data)
        os.replace(tmp_jar, jar_path)


def add_props(root: str) -> bool:
    keys = {
        "fw.max_users": "8",
        "fw.show_multiuserui": "1",
        "fw.show_hidden_users": "1",
    }
    wrote = False
    for dirpath, _, files in os.walk(root):
        if "build.prop" not in files:
            continue
        path = os.path.join(dirpath, "build.prop")
        text = open(path, encoding="utf-8", errors="replace").read()
        extra = []
        for key, value in keys.items():
            if key + "=" not in text:
                extra.append(key + "=" + value)
        if extra:
            with open(path, "a", encoding="utf-8", newline="\n") as handle:
                handle.write("\n" + "\n".join(extra) + "\n")
            wrote = True
            print("props", path)
    return wrote


def main() -> None:
    root = sys.argv[1]
    jars = []
    for dirpath, _, files in os.walk(root):
        if "framework.jar" in files and "framework" in dirpath.replace("\\", "/").split(
            "/"
        ):
            jars.append(os.path.join(dirpath, "framework.jar"))
    if not jars:
        raise SystemExit("framework.jar not found under " + root)
    tool_dir = os.path.join(_SCRIPTS, "..", "prebuilts", "smali")
    patch_jar(jars[0], tool_dir)
    add_props(root)
    print("multi-user enabled")


if __name__ == "__main__":
    main()
