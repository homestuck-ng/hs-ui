#!/usr/bin/env python3
"""Unpack an Android super image. Linear extents only."""
import argparse
import os
import struct
import sys

GEOM_MAGIC = 0x616C4467
HDR_MAGIC = 0x414C5030
RESERVED = 4096
GEOM_SIZE = 4096
LINEAR = 0
ZERO = 1


def read_geom(f, off):
    f.seek(off)
    buf = f.read(52)
    if len(buf) < 52:
        return None
    magic, size = struct.unpack_from("<II", buf, 0)
    if magic != GEOM_MAGIC or size < 52:
        return None
    max_size, slots, block = struct.unpack_from("<III", buf, 40)
    if slots < 1 or slots > 4 or max_size < 512 or block != 4096:
        return None
    return max_size, slots


def cstr(raw):
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace")


def parse_header(blob):
    magic, major, minor, header_size = struct.unpack_from("<IHH I", blob, 0)
    if magic != HDR_MAGIC:
        raise SystemExit("super metadata magic mismatch")
    if header_size < 128 or header_size > len(blob):
        raise SystemExit(f"bad header_size {header_size}")
    tables_size = struct.unpack_from("<I", blob, 44)[0]
    tables = blob[header_size:header_size + tables_size]
    if len(tables) < tables_size:
        raise SystemExit("truncated metadata tables")
    descs = []
    off = 80
    for _ in range(4):
        descs.append(struct.unpack_from("<III", blob, off))
        off += 12
    return tables, descs, major, minor


def entries(tables, desc, size):
    offset, count, entry_size = desc
    if entry_size < size:
        raise SystemExit(f"entry {entry_size} < {size}")
    out = []
    for i in range(count):
        start = offset + i * entry_size
        out.append(tables[start:start + entry_size])
    return out


def unpack(image, outdir, names):
    os.makedirs(outdir, exist_ok=True)
    size = os.path.getsize(image)
    with open(image, "rb") as f:
        geom = read_geom(f, RESERVED) or read_geom(f, size - GEOM_SIZE)
        if geom is None:
            raise SystemExit("LP geometry not found")
        max_size, slots = geom
        meta = None
        for slot in range(slots):
            off = RESERVED + GEOM_SIZE + slot * max_size
            f.seek(off)
            blob = f.read(max_size)
            if len(blob) >= 4 and struct.unpack_from("<I", blob, 0)[0] == HDR_MAGIC:
                meta = blob
                break
        if meta is None:
            raise SystemExit("LP header not found")
        tables, descs, major, minor = parse_header(meta)
        parts = entries(tables, descs[0], 52)
        extents = entries(tables, descs[1], 24)
        print(f"metadata {major}.{minor} partitions {len(parts)} extents {len(extents)}")
        wanted = set(names) if names else None
        for raw in parts:
            name = cstr(raw[:36])
            first, count = struct.unpack_from("<II", raw, 40)
            if wanted is not None and name not in wanted:
                continue
            dest = os.path.join(outdir, name + ".img")
            total = 0
            with open(dest, "wb") as out:
                for idx in range(first, first + count):
                    ext = extents[idx]
                    sectors, kind, target, source = struct.unpack_from("<QIQI", ext, 0)
                    nbytes = sectors * 512
                    if kind == ZERO:
                        remain = nbytes
                        while remain:
                            chunk = min(remain, 1024 * 1024)
                            out.write(b"\x00" * chunk)
                            remain -= chunk
                    elif kind == LINEAR:
                        f.seek(target * 512)
                        remain = nbytes
                        while remain:
                            chunk = f.read(min(remain, 1024 * 1024))
                            if not chunk:
                                raise SystemExit(f"{name} short read")
                            out.write(chunk)
                            remain -= len(chunk)
                    else:
                        raise SystemExit(f"{name} extent type {kind} source {source}")
                    total += nbytes
            print(f"{name} {total}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("outdir")
    p.add_argument("names", nargs="*")
    args = p.parse_args()
    unpack(args.image, args.outdir, args.names)


if __name__ == "__main__":
    sys.exit(main())
