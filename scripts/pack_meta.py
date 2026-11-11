#!/usr/bin/env python3
"""Write the dynamic-partition metadata and updater-script for the r0q zip."""
import hashlib
import os
import struct
import sys

ORDER = ["system", "vendor", "product", "system_ext", "odm", "vendor_dlkm"]


def name36(text):
    raw = text.encode()
    return raw + b"\x00" * (36 - len(raw))


def main():
    stage, group_s, device_s = sys.argv[1:4]
    group = int(group_s)
    device_size = int(device_s)
    sizes = {}
    for name in ORDER:
        path = os.path.join(stage, name + ".img")
        size = os.path.getsize(path)
        if size % 4096:
            raise SystemExit(f"{name} size {size} is not 4096-aligned")
        sizes[name] = size
        print(name, size)
    total = sum(sizes.values())
    print("occupied", total, "group", group)
    if total > group:
        raise SystemExit("images exceed the super group")

    meta_max = 65536
    slots = 2
    logical = 4096
    reserved = 4096 + (4096 + meta_max * slots) * 2
    align = 1024 * 1024
    free = (reserved + align - 1) & ~(align - 1)
    first_sector = free // 512
    geom = struct.pack("<II32sIII", 0x616C4467, 52, b"\x00" * 32, meta_max, slots, logical)
    geom = struct.pack("<II32sIII", 0x616C4467, 52, hashlib.sha256(geom).digest(), meta_max, slots, logical)
    geom = geom.ljust(4096, b"\x00")
    groups = name36("default") + struct.pack("<IQ", 0, 0)
    groups += name36("qti_dynamic_partitions") + struct.pack("<IQ", 0, group)
    parts = b""
    for name in ORDER:
        parts += name36(name) + struct.pack("<IIII", 1, 0, 0, 1)
    device = struct.pack("<QIIQ", first_sector, align, 0, device_size) + name36("super") + struct.pack("<I", 0)
    tables = parts + groups + device
    tsha = hashlib.sha256(tables).digest()
    poff = 0
    eoff = len(parts)
    goff = eoff
    boff = goff + len(groups)
    def header(hsha):
        blob = struct.pack("<IHH I 32s I 32s", 0x414C5030, 10, 0, 128, hsha, len(tables), tsha)
        blob += struct.pack("<III", poff, len(ORDER), 52)
        blob += struct.pack("<III", eoff, 0, 24)
        blob += struct.pack("<III", goff, 2, 48)
        blob += struct.pack("<III", boff, 1, 64)
        return blob
    hdr = header(hashlib.sha256(header(b"\x00" * 32)).digest())
    open(os.path.join(stage, "unsparse_super_empty.img"), "wb").write(geom + hdr + tables)
    lines = [
        "# Remove all existing dynamic partitions and groups before applying full OTA",
        "remove_all_groups",
        f"# Add group qti_dynamic_partitions with maximum size {group}",
        f"add_group qti_dynamic_partitions {group}",
    ]
    for name in ORDER:
        lines += [f"# Add partition {name} to group qti_dynamic_partitions", f"add {name} qti_dynamic_partitions"]
    for name in ORDER:
        lines += [f"# Grow partition {name} from 0 to {sizes[name]}", f"resize {name} {sizes[name]}"]
    open(os.path.join(stage, "dynamic_partitions_op_list"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    script = [
        'getprop("ro.boot.em.model") == "SM-S901E" || getprop("ro.product.device") == "r0q" || getprop("ro.product.device") == "r0qxxx" || abort("E3004: This package is for r0q / SM-S901E.");',
        'ui_print("OneUI 5.1 hybrid r0q, binary C boot. Do not flash BL or CP.");',
        'ui_print("Wi-Fi calling, location, emergency, Knox Guard and DeX stay.");',
        'assert(update_dynamic_partitions(package_extract_file("dynamic_partitions_op_list"), package_extract_file("unsparse_super_empty.img")));',
    ]
    for name in ORDER:
        script.append(f'ui_print("Patching {name} ...");')
        script.append(
            f'block_image_update(map_partition("{name}"), package_extract_file("{name}.transfer.list"), "{name}.new.dat.br", "{name}.patch.dat") || abort("E1001: Failed to update {name} image.");'
        )
    for img, part in (
        ("dtbo.img", "dtbo"),
        ("vendor_boot.img", "vendor_boot"),
        ("boot.img", "boot"),
        ("vbmeta.img", "vbmeta"),
        ("vbmeta_system.img", "vbmeta_system"),
    ):
        script.append(f'ui_print("Writing {img}...");')
        script.append(f'package_extract_file("{img}", "/dev/block/bootdevice/by-name/{part}");')
    script += [
        "set_progress(1.000000);",
        'ui_print("Done. Do not flash BL/CP. Format data if this is a new install.");',
    ]
    meta = os.path.join(stage, "META-INF", "com", "google", "android")
    os.makedirs(meta, exist_ok=True)
    open(os.path.join(meta, "updater-script"), "w", encoding="utf-8").write("\n".join(script) + "\n")
    print("META_OK")


if __name__ == "__main__":
    main()
