#!/usr/bin/env python3
"""Record uid, gid, mode and xattrs from a mounted firmware image.

UN1CA writes the same data to fs_config and file_context before it rebuilds
the partition. The GitHub runner extracts files as its own uid, so the image
rebuild has to put the original owners back.
"""
import json
import os
import sys


def xattr(path, name):
    try:
        return os.getxattr(path, name, follow_symlinks=False)
    except OSError:
        return b""


def record(path, root, out):
    rel = os.path.relpath(path, root)
    if rel == ".":
        rel = ""
    st = os.lstat(path)
    out.write(json.dumps({
        "p": rel,
        "u": st.st_uid,
        "g": st.st_gid,
        "m": st.st_mode & 0o7777,
        "s": xattr(path, "security.selinux").decode("utf-8", "surrogateescape"),
        "c": list(xattr(path, "security.capability")),
    }, ensure_ascii=True) + "\n")


def main():
    root, dest = sys.argv[1:]
    n = 0
    with open(dest, "w", encoding="utf-8") as out:
        record(root, root, out)
        n += 1
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            for name in dirnames + filenames:
                record(os.path.join(dirpath, name), root, out)
                n += 1
    print("meta", dest, n)


if __name__ == "__main__":
    main()
