#!/usr/bin/env python3
"""Enable Samsung multi-user the way UN1CA does.

Samsung phones force a single user unless the build looks like a tablet.
The framework helper is flipped so the user cap is 8 and the switcher is on.
"""
import os
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

SMALI_VER = "2.5.2"
SMALI_URL = "https://github.com/baksmali/smali/releases/download/v{0}/smali-{0}.jar"
BAKSMALI_URL = "https://github.com/baksmali/smali/releases/download/v{0}/baksmali-{0}.jar"

CLINIT = """.method static constructor <clinit>()V
    .locals 2

    const/4 v0, 0x1

    sput-boolean v0, Lcom/samsung/android/core/pm/multiuser/MultiUserSupportsHelper;->IS_TABLET:Z

    const/16 v1, 0x8

    sput v1, Lcom/samsung/android/core/pm/multiuser/MultiUserSupportsHelper;->DEFAULT_MAX_USERS:I

    sput-boolean v0, Lcom/samsung/android/core/pm/multiuser/MultiUserSupportsHelper;->DEFAULT_ENABLE_STATUS:Z

    return-void
.end method
"""


def rewrite_smali(text):
    start = text.find(".method static constructor <clinit>()V")
    if start < 0:
        return None
    end = text.find(".end method", start)
    if end < 0:
        return None
    end += len(".end method")
    body = text[start:end]
    if "DEFAULT_MAX_USERS" not in body or "IS_TABLET" not in body:
        return None
    if "const/16 v1, 0x8" in body and "const/4 v0, 0x1" in body and "ro.build.characteristics" not in body:
        return text
    return text[:start] + CLINIT.strip() + text[end:]


def ensure_jar(url, dest):
    if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    return dest


def run(args):
    subprocess.check_call(args)


def patch_jar(jar_path, tool_dir):
    baksmali = ensure_jar(BAKSMALI_URL.format(SMALI_VER), os.path.join(tool_dir, "baksmali.jar"))
    smali = ensure_jar(SMALI_URL.format(SMALI_VER), os.path.join(tool_dir, "smali.jar"))
    with zipfile.ZipFile(jar_path) as archive:
        dexes = [name for name in archive.namelist() if name.startswith("classes") and name.endswith(".dex")]
    if not dexes:
        raise SystemExit("no dex in " + jar_path)
    changed = False
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(jar_path) as archive:
            archive.extractall(tmp, dexes)
        for dex in dexes:
            dex_path = os.path.join(tmp, dex)
            smali_dir = os.path.join(tmp, dex + ".out")
            run(["java", "-jar", baksmali, "d", dex_path, "-o", smali_dir])
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
            run(["java", "-jar", smali, "a", smali_dir, "-o", dex_path])
            changed = True
            print("patched", dex)
            break
        if not changed:
            raise SystemExit("MultiUserSupportsHelper.smali was not found")
        tmp_jar = jar_path + ".tmp"
        with zipfile.ZipFile(jar_path, "r") as src, zipfile.ZipFile(tmp_jar, "w") as dst:
            for info in src.infolist():
                data = open(os.path.join(tmp, info.filename), "rb").read() if info.filename in dexes else src.read(info.filename)
                dst.writestr(info, data)
        os.replace(tmp_jar, jar_path)


def add_props(root):
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


def main():
    root = sys.argv[1]
    jars = []
    for dirpath, _, files in os.walk(root):
        if "framework.jar" in files and "framework" in dirpath.replace("\\", "/").split("/"):
            jars.append(os.path.join(dirpath, "framework.jar"))
    if not jars:
        raise SystemExit("framework.jar not found under " + root)
    tool_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prebuilts", "smali")
    patch_jar(jars[0], tool_dir)
    add_props(root)
    print("multi-user enabled")


if __name__ == "__main__":
    main()
