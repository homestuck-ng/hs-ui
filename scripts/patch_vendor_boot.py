#!/usr/bin/env python3
"""Drop userdata encryption from the vendor_boot fstab.

Partitions stay f2fs, same as the images. Init on this bootloader uses the
first fstab line for a mount point, so the line is not rewritten to erofs.
"""
import os
import struct
import subprocess
import sys

from strip_userdata_encryption import strip_line

PAGE = 4096


def align(n):
    return (n + PAGE - 1) & ~(PAGE - 1)


def parse_header(buf):
    if buf[:8] != b"VNDRBOOT":
        raise SystemExit("not a vendor_boot image")
    page, ramdisk_size = struct.unpack_from("<I", buf, 12)[0], struct.unpack_from("<I", buf, 24)[0]
    off = 28 + 2048 + 4 + 16
    header_size, dtb_size = struct.unpack_from("<2I", buf, off)
    off += 16
    table_size, table_num, entry_size, bootconfig_size = struct.unpack_from("<4I", buf, off)
    return dict(page=page, ramdisk_size=ramdisk_size, header_size=header_size,
                dtb_size=dtb_size, table_size=table_size, table_num=table_num,
                entry_size=entry_size, bootconfig_size=bootconfig_size)


def rewrite(text):
    changed = False
    out = []
    for line in text.splitlines(keepends=True):
        stripped = strip_line(line)
        if stripped != line:
            changed = True
            line = stripped
        if "userdata" in line and not line.lstrip().startswith("#"):
            print(line.rstrip("\n"))
        out.append(line)
    return "".join(out), changed


def read_cpio(blob):
    files = []
    pos = 0
    while pos + 110 <= len(blob):
        if blob[pos:pos + 6] != b"070701":
            break
        fields = [int(blob[pos + 6 + 8 * k:pos + 6 + 8 * (k + 1)], 16) for k in range(13)]
        namesize, filesize = fields[11], fields[6]
        name_off = pos + 110
        name = blob[name_off:name_off + namesize].split(b"\x00", 1)[0].decode("utf-8", "replace")
        data_off = (name_off + namesize + 3) & ~3
        data = blob[data_off:data_off + filesize]
        pos = (data_off + filesize + 3) & ~3
        files.append((fields, name, data))
        if name == "TRAILER!!!":
            break
    return files


def write_cpio(files):
    out = bytearray()
    for fields, name, data in files:
        name_b = name.encode() + b"\x00"
        fields = list(fields)
        fields[6] = len(data)
        fields[11] = len(name_b)
        out += b"070701" + b"".join(f"{v:08X}".encode() for v in fields)
        out += name_b
        out += b"\x00" * ((4 - (len(out) & 3)) & 3)
        out += data
        out += b"\x00" * ((4 - (len(out) & 3)) & 3)
    return bytes(out)


def main():
    src, dest, work = sys.argv[1:4]
    os.makedirs(work, exist_ok=True)
    blob = open(src, "rb").read()
    h = parse_header(blob)
    page = h["page"] or PAGE
    ram_off = page
    dtb_off = align(ram_off + h["ramdisk_size"])
    table_off = align(dtb_off + h["dtb_size"])
    bootcfg_off = align(table_off + h["table_size"])
    ram = blob[ram_off:ram_off + h["ramdisk_size"]]
    dtb = blob[dtb_off:dtb_off + h["dtb_size"]]
    table = bytearray(blob[table_off:table_off + h["table_size"]])
    bootcfg = blob[bootcfg_off:bootcfg_off + h["bootconfig_size"]]
    es = h["entry_size"]
    slices = []
    patched = False
    for i in range(h["table_num"]):
        ent = table[i * es:(i + 1) * es]
        size, offset, rtype = struct.unpack_from("<3I", ent, 0)
        piece = ram[offset:offset + size]
        raw = os.path.join(work, f"rd{i}.cpio")
        comp = os.path.join(work, f"rd{i}.lz4")
        open(comp, "wb").write(piece)
        subprocess.check_call(["lz4", "-d", "-f", comp, raw])
        files = read_cpio(open(raw, "rb").read())
        changed = False
        new_files = []
        for fields, name, data in files:
            if name.endswith("fstab.qcom") or name.endswith("fstab.qcom.vendor"):
                text, did = rewrite(data.decode("utf-8", "replace"))
                if did:
                    print("patched", name)
                    data = text.encode()
                    changed = True
                    patched = True
            new_files.append((fields, name, data))
        if not changed:
            slices.append(piece)
            continue
        new_raw = os.path.join(work, f"rd{i}.new.cpio")
        new_lz4 = os.path.join(work, f"rd{i}.new.lz4")
        open(new_raw, "wb").write(write_cpio(new_files))
        subprocess.check_call(["lz4", "-l", "-9", "-f", new_raw, new_lz4])
        slices.append(open(new_lz4, "rb").read())
    if not patched:
        raise SystemExit("fstab was not patched")
    new_ram = bytearray()
    new_table = bytearray(table)
    for i, sl in enumerate(slices):
        struct.pack_into("<2I", new_table, i * es, len(sl), len(new_ram))
        new_ram += sl
    header = bytearray(blob[:page])
    struct.pack_into("<I", header, 24, len(new_ram))
    out = bytearray(header[:page])
    out += new_ram
    out += b"\x00" * (align(len(out)) - len(out))
    out += dtb
    out += b"\x00" * (align(len(out)) - len(out))
    out += new_table
    out += b"\x00" * (align(len(out)) - len(out))
    out += bootcfg
    if len(out) < len(blob):
        out += b"\x00" * (len(blob) - len(out))
    elif len(out) > len(blob):
        raise SystemExit(f"vendor_boot grew {len(blob)} -> {len(out)}")
    open(dest, "wb").write(out)
    print("vendor_boot", len(out))


if __name__ == "__main__":
    main()
