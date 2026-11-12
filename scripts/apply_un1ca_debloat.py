#!/usr/bin/env python3
"""Delete the UN1CA r0q debloat paths and the dexpreopt leftovers.

The path list is unica/debloat.sh plus target/r0q/debloat.sh. A missing
path is skipped: this tree is One UI 5.1, and a few UN1CA names belong
to a newer source. The signed apex files are not touched.
"""
import os
import shutil
import subprocess
import sys


def package_of(apk):
    try:
        out = subprocess.check_output(
            ["aapt", "dump", "badging", apk],
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for line in out.decode("utf-8", "replace").splitlines():
        if not line.startswith("package:"):
            continue
        for part in line.split():
            if part.startswith("name="):
                return part.split("=", 1)[1].strip("'\"")
    return None


def packages_under(path):
    found = []
    if os.path.isfile(path) and path.endswith(".apk"):
        pkg = package_of(path)
        if pkg:
            found.append(pkg)
        return found
    if not os.path.isdir(path):
        return found
    for dirpath, _, filenames in os.walk(path):
        for name in filenames:
            if name.endswith(".apk"):
                pkg = package_of(os.path.join(dirpath, name))
                if pkg:
                    found.append(pkg)
    return found


def remove_path(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def load_list(path):
    entries = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            part, rel = line.split(None, 1)
            entries.append((part, rel))
    return entries


def main():
    root, list_path, log_path = sys.argv[1:4]
    removed = []
    packages = []
    for part, rel in load_list(list_path):
        path = os.path.join(root, part, rel)
        if not os.path.lexists(path):
            print("skip", part, rel, flush=True)
            continue
        packages.extend(packages_under(path))
        remove_path(path)
        removed.append(f"# {part}/{rel}")
        print("DEL", part, rel, flush=True)

    for part in ("system", "product", "system_ext"):
        base = os.path.join(root, part)
        if not os.path.isdir(base):
            continue
        oats = []
        for dirpath, dirnames, _ in os.walk(base):
            if "oat" in dirnames:
                oats.append(os.path.join(dirpath, "oat"))
        for path in oats:
            if os.path.isdir(path):
                shutil.rmtree(path)
                removed.append(f"# {os.path.relpath(path, root)}")
                print("DEL oat", path, flush=True)

    system = os.path.join(root, "system")
    for rel in (
        "system/etc/boot-image.bprof",
        "system/etc/boot-image.prof",
        "system/framework/arm",
        "system/framework/arm64",
    ):
        path = os.path.join(system, rel)
        if os.path.lexists(path):
            remove_path(path)
            removed.append(f"# {rel}")
            print("DEL", rel, flush=True)
    framework = os.path.join(system, "system", "framework")
    if os.path.isdir(framework):
        for name in os.listdir(framework):
            if name.endswith(".vdex"):
                os.remove(os.path.join(framework, name))
                removed.append(f"# system/framework/{name}")
                print("DEL vdex", name, flush=True)

    unique = []
    seen = set()
    for pkg in packages:
        if pkg not in seen:
            seen.add(pkg)
            unique.append(pkg)
            removed.append(pkg + " un1ca")
    with open(log_path, "a", encoding="utf-8") as handle:
        if removed:
            handle.write("\n".join(removed) + "\n")
    print("un1ca removed paths", len(removed), "packages", len(unique))


if __name__ == "__main__":
    main()
