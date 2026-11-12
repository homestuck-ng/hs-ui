#!/usr/bin/env python3
"""Keep userdata as the plain f2fs image that is already on the phone.

Stock fstab mounts /data, then init sees fileencryption= and
metadata_encryption=, unmounts it, and turns on FBE. /data/vendor from
the installed apps is not empty, so the new policy fails and init
reboots to recovery.
"""
import os
import re
import sys

FLAGS = ("fileencryption", "metadata_encryption", "keydirectory")
FLAG_RE = re.compile(r",?(?:" + "|".join(FLAGS) + r")=[^,\s]*")


def strip_line(line: str) -> str:
    if "userdata" not in line or line.lstrip().startswith("#"):
        return line
    new = FLAG_RE.sub("", line)
    new = new.replace(",,", ",")
    return new


def main() -> None:
    root = sys.argv[1]
    changed = 0
    for dirpath, _, files in os.walk(root):
        for name in files:
            if not name.startswith("fstab."):
                continue
            path = os.path.join(dirpath, name)
            text = open(path, encoding="utf-8", errors="surrogateescape").read()
            new = "".join(strip_line(line) for line in text.splitlines(keepends=True))
            if new == text:
                continue
            open(path, "w", encoding="utf-8", errors="surrogateescape").write(new)
            changed += 1
            for line in new.splitlines():
                if "userdata" in line and not line.lstrip().startswith("#"):
                    print(path)
                    print(line)
    if changed == 0:
        raise SystemExit(f"no userdata encryption flags found under {root}")
    print("fstabs", changed)


if __name__ == "__main__":
    main()
