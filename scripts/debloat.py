#!/usr/bin/env python3
"""Delete junk app directories. KEEP always wins."""
import os
import subprocess
import sys


def load(path):
    names = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line)
    return names


def package_of(apk):
    try:
        out = subprocess.check_output(
            ["aapt", "dump", "badging", apk],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    for line in out.decode("utf-8", "replace").splitlines():
        if line.startswith("package:"):
            for part in line.split():
                if part.startswith("name="):
                    return part.split("=", 1)[1].strip("'\"")
    return None


def main():
    root, remove_path, keep_path, log_path = sys.argv[1:5]
    remove = load(remove_path)
    keep = load(keep_path)
    removed = []
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git"}]
        for name in filenames:
            if not name.endswith(".apk"):
                continue
            apk = os.path.join(dirpath, name)
            pkg = package_of(apk)
            if not pkg or pkg in seen:
                continue
            seen.add(pkg)
            if pkg in keep or pkg not in remove:
                continue
            app_dir = dirpath
            # priv-app/Name/Name.apk -> delete priv-app/Name
            if os.path.basename(os.path.dirname(app_dir)) in {"app", "priv-app", "overlay"}:
                app_dir = dirpath
            print("DEL", pkg, app_dir, flush=True)
            removed.append(pkg + " " + os.path.relpath(app_dir, root))
            # walk will still visit deleted dirs; ignore the error
            subprocess.check_call(["rm", "-rf", app_dir])
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(removed) + ("\n" if removed else ""))
    for pkg in ("com.sec.unifiedwfc", "com.samsung.android.kgclient", "com.sec.epdg"):
        if pkg not in seen:
            raise SystemExit(f"{pkg} was not found in the tree")
        if any(line.startswith(pkg + " ") for line in removed):
            raise SystemExit(f"refusing to ship without {pkg}")
    print("removed", len(removed), "scanned", len(seen))


if __name__ == "__main__":
    main()
