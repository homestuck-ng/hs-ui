#!/usr/bin/env python3
"""Put the recorded owners and SELinux labels back onto a new f2fs image."""
import json
import os
import stat
import sys


def main():
    root, meta = sys.argv[1], sys.argv[2]
    kind = sys.argv[3] if len(sys.argv) > 3 else "all"
    n = 0
    missing = 0
    with open(meta, encoding="utf-8") as fh:
        for line in fh:
            item = json.loads(line)
            rel = item["p"]
            path = root if rel == "" else os.path.join(root, rel)
            if not os.path.lexists(path):
                missing += 1
                continue
            if kind != "labels":
                os.lchown(path, item["u"], item["g"])
                if not stat.S_ISLNK(os.lstat(path).st_mode):
                    os.chmod(path, item["m"])
            if kind != "owners":
                sel = item["s"].encode("utf-8", "surrogateescape")
                if sel:
                    os.setxattr(path, "security.selinux", sel, follow_symlinks=False)
                cap = bytes(item["c"])
                if cap:
                    os.setxattr(path, "security.capability", cap, follow_symlinks=False)
            n += 1
    print("restored", n, "skipped", missing)
    logd = os.path.join(root, "system", "bin", "logd")
    if os.path.lexists(logd):
        st = os.lstat(logd)
        print("logd", oct(st.st_mode & 0o7777), st.st_uid, st.st_gid)


if __name__ == "__main__":
    main()
