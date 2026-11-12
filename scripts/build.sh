#!/usr/bin/env bash
# Build the SM-S901E One UI 5.1 hybrid zip.
# Firmware is fetched with ananjaser1211/samloader, the same tool UN1CA sixteen calls.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/target/r0q/config.sh"

WORK="$ROOT/work"
OUT="$ROOT/out"
SYS="$WORK/fw51"
BOOT="$WORK/fw61"
TREE="$WORK/tree"
STAGE="$WORK/stage"
mkdir -p "$WORK" "$OUT" "$TREE" "$STAGE/META-INF/com/google/android"

if ! command -v samloader >/dev/null 2>&1; then
    python3 -m pip install --upgrade --break-system-packages "samloader @ git+https://github.com/ananjaser1211/samloader.git"
fi

download_tagged() {
    local tag="$1" fw="$2" dest="$3"
    bash "$ROOT/scripts/download_fw.sh" "$fw" "$dest" 2>&1 | sed -u "s/^/[$tag] /"
}
download_tagged "5.1" "$SYSTEM_FW" "$SYS" &
pid51=$!
download_tagged "6.1" "$BOOT_FW" "$BOOT" &
pid61=$!
fail=0
wait "$pid51" || fail=1
wait "$pid61" || fail=1
if ((fail)); then
    echo "firmware download failed" >&2
    exit 1
fi

unpack_ap() {
    local dest="$1"
    local ap
    ap="$(find "$dest" -maxdepth 1 \( -name 'AP_*.tar.md5' -o -name 'AP_*.tar' \) | head -n 1)"
    [[ -n "$ap" ]] || { echo "no AP in $dest" >&2; exit 1; }
    rm -rf "$dest/ap"
    mkdir -p "$dest/ap"
    tar -xf "$ap" -C "$dest/ap"
    rm -f "$ap"
    local img
    for img in boot dtbo vendor_boot vbmeta vbmeta_system super; do
        if [[ -f "$dest/ap/${img}.img.lz4" ]]; then
            lz4 -d -f "$dest/ap/${img}.img.lz4" "$dest/${img}.img"
            rm -f "$dest/ap/${img}.img.lz4"
        elif [[ -f "$dest/ap/${img}.img" ]]; then
            mv "$dest/ap/${img}.img" "$dest/${img}.img"
        fi
    done
    rm -rf "$dest/ap"
}

unsparse() {
    local img="$1"
    if [[ "$(python3 "$ROOT/scripts/image_kind.py" "$img")" == "sparse" ]]; then
        simg2img "$img" "$img.raw"
        mv "$img.raw" "$img"
    fi
}

extract_fs() {
    local img="$1"
    local dest="$2"
    unsparse "$img"
    local kind
    kind="$(python3 "$ROOT/scripts/image_kind.py" "$img")"
    rm -rf "$dest"
    mkdir -p "$dest"
    echo "extract $kind $img"
    case "$kind" in
        erofs)
            if ! fsck.erofs --extract="$dest" "$img"; then
                rm -rf "$dest"
                mkdir -p "$dest"
                dump.erofs --extract="$dest" "$img"
            fi
            ;;
        f2fs|ext4)
            local mnt="$WORK/mnt"
            mkdir -p "$mnt"
            sudo umount "$mnt" 2>/dev/null || true
            sudo mount -o ro,loop "$img" "$mnt"
            sudo cp -a "$mnt"/. "$dest"/
            sudo umount "$mnt"
            sudo chown -R "$(id -u):$(id -g)" "$dest"
            ;;
        *)
            echo "unknown filesystem $img ($kind)" >&2
            exit 1
            ;;
    esac
}

echo "=== unpack AP ==="
unpack_ap "$SYS"
unpack_ap "$BOOT"
unsparse "$SYS/super.img"
unsparse "$BOOT/super.img"
python3 "$ROOT/scripts/lpunpack.py" "$SYS/super.img" "$SYS/parts" system vendor product system_ext odm
python3 "$ROOT/scripts/lpunpack.py" "$BOOT/super.img" "$BOOT/parts" vendor_dlkm
rm -f "$SYS/super.img" "$BOOT/super.img"

echo "=== extract filesystems ==="
extract_fs "$SYS/parts/system.img" "$TREE/system"
extract_fs "$SYS/parts/product.img" "$TREE/product"
extract_fs "$SYS/parts/system_ext.img" "$TREE/system_ext"
extract_fs "$SYS/parts/vendor.img" "$TREE/vendor"
extract_fs "$BOOT/parts/vendor_dlkm.img" "$TREE/vendor_dlkm"
unsparse "$SYS/parts/odm.img"
cp -a "$SYS/parts/odm.img" "$WORK/odm.img"
rm -rf "$SYS/parts" "$BOOT/parts"

echo "=== debloat and vintf ==="
python3 "$ROOT/scripts/debloat.py" "$TREE" \
    "$ROOT/target/r0q/remove.list" "$ROOT/target/r0q/keep.list" "$STAGE/debloat.txt"
MAN="$TREE/vendor/etc/vintf/manifest"
rm -f \
    "$MAN/vendor.samsung.hardware.sehradio_manifest_2_31.xml" \
    "$MAN/vendor.samsung.hardware.radio_manifest_2_31.xml" \
    "$MAN/vendor.samsung.hardware.radio.exclude.qcom.xml" \
    "$MAN/iweaver_v1_manifest.xml"
python3 "$ROOT/scripts/vermagic.py" "$TREE/vendor_dlkm"

PLAT="$(find "$TREE/system" -path '*/etc/selinux/plat_file_contexts' | head -n 1)"
VFC="$(find "$TREE/vendor" -path '*/etc/selinux/vendor_file_contexts' | head -n 1)"
[[ -n "$PLAT" && -n "$VFC" ]] || { echo "file_contexts missing" >&2; exit 1; }
# Keep durable copies: mk_erofs deletes $TREE/system after system.erofs, but
# product/system_ext still need the same plat_file_contexts path.
cp -a "$PLAT" "$WORK/plat_fc"
PLAT="$WORK/plat_fc"
cat "$PLAT" "$VFC" > "$WORK/vendor_fc"
if [[ -f "$MAN/iweaver_v1_manifest.xml" ]]; then
    echo '/(vendor|system/vendor)/etc/vintf/manifest/iweaver_v1_manifest\.xml u:object_r:vendor_configs_file:s0' >> "$WORK/vendor_fc"
fi

pad4k() {
    python3 - "$1" <<'PY'
import os, sys
path = sys.argv[1]
size = os.path.getsize(path)
extra = (-size) % 4096
if extra:
    with open(path, "ab") as f:
        f.write(b"\x00" * extra)
print(path, os.path.getsize(path))
PY
}

mk_erofs() {
    local mount="$1" contexts="$2" image="$3" tree="$4"
    rm -f "$image"
    # dump.erofs/fsck.erofs --extract on GHA runs as uid 1001 (runner=radio).
    # Baking that into erofs makes mode-750 bins (logd etc.) unexecutable by their
    # service uids → init: cannot execv(...): Permission denied and a stuck boot.
    mkfs.erofs -zlz4hc,9 -b 4096 --mount-point="$mount" \
        --file-contexts="$contexts" --all-root -T 1640995200 \
        "$image" "$tree"
    pad4k "$image"
}

echo "=== framework patches ==="
python3 "$ROOT/scripts/enable_multiuser.py" "$TREE/system"
python3 "$ROOT/scripts/patch_bluetooth_lib.py" "$TREE"
python3 "$ROOT/scripts/apply_deknox.py" "$TREE"

echo "=== erofs ==="
mk_erofs / "$PLAT" "$WORK/system.erofs" "$TREE/system"
rm -rf "$TREE/system"
mk_erofs /product "$PLAT" "$WORK/product.erofs" "$TREE/product"
rm -rf "$TREE/product"
mk_erofs /system_ext "$PLAT" "$WORK/system_ext.erofs" "$TREE/system_ext"
rm -rf "$TREE/system_ext"
mk_erofs /vendor "$WORK/vendor_fc" "$WORK/vendor.erofs" "$TREE/vendor"
rm -rf "$TREE/vendor"

echo "=== vendor_dlkm ==="
DLKM="$WORK/vendor_dlkm.img"
rm -f "$DLKM"
truncate -s "$VENDOR_DLKM_BYTES" "$DLKM"
mkfs.f2fs -q -f -l vendor_dlkm -o 8 "$DLKM"
MNT="$WORK/mnt"
mkdir -p "$MNT"
sudo umount "$MNT" 2>/dev/null || true
sudo mount -t f2fs -o loop "$DLKM" "$MNT"
sudo cp -a "$TREE/vendor_dlkm"/. "$MNT"/
sudo python3 - "$MNT" <<'PY'
import os, sys
root = sys.argv[1]
ctx = b"u:object_r:vendor_file:s0\x00"
for dirpath, dirnames, filenames in os.walk(root):
    os.setxattr(dirpath, "security.selinux", ctx)
    for name in dirnames + filenames:
        os.setxattr(os.path.join(dirpath, name), "security.selinux", ctx)
print("labels ok")
PY
sudo umount "$MNT"
rm -rf "$TREE/vendor_dlkm"
pad4k "$DLKM"
pad4k "$WORK/odm.img"

echo "=== boot and vbmeta ==="
cp -a "$BOOT/boot.img" "$STAGE/boot.img"
cp -a "$BOOT/dtbo.img" "$STAGE/dtbo.img"
python3 "$ROOT/scripts/patch_vendor_boot.py" \
    "$BOOT/vendor_boot.img" "$STAGE/vendor_boot.img" "$WORK/vbpatch"
python3 "$ROOT/scripts/vbmeta_patch.py" "$SYS/vbmeta.img" "$STAGE/vbmeta.img"
python3 "$ROOT/scripts/vbmeta_patch.py" "$SYS/vbmeta_system.img" "$STAGE/vbmeta_system.img"
rm -rf "$SYS" "$BOOT" "$WORK/vbpatch"

ln -sfn "$WORK/system.erofs" "$STAGE/system.img"
ln -sfn "$WORK/product.erofs" "$STAGE/product.img"
ln -sfn "$WORK/system_ext.erofs" "$STAGE/system_ext.img"
ln -sfn "$WORK/vendor.erofs" "$STAGE/vendor.img"
ln -sfn "$WORK/odm.img" "$STAGE/odm.img"
ln -sfn "$DLKM" "$STAGE/vendor_dlkm.img"
python3 "$ROOT/scripts/pack_meta.py" "$STAGE" "$GROUP_SIZE" "$SUPER_SIZE"

to_dat() {
    local name="$1"
    local img="$2"
    python3 "$ROOT/external/img2sdat/img2sdat" -o "$STAGE" -v 4 "$STAGE/${name}.img"
    brotli --quality=6 --output="$STAGE/${name}.new.dat.br" "$STAGE/${name}.new.dat"
    rm -f "$STAGE/${name}.new.dat" "$STAGE/${name}.img" "$img"
    echo "dat $name"
}

echo "=== dat ==="
to_dat system "$WORK/system.erofs"
to_dat product "$WORK/product.erofs"
to_dat system_ext "$WORK/system_ext.erofs"
to_dat vendor "$WORK/vendor.erofs"
to_dat odm "$WORK/odm.img"
to_dat vendor_dlkm "$DLKM"

cp -a "$ROOT/prebuilts/updater" "$STAGE/META-INF/com/google/android/update-binary"
chmod 755 "$STAGE/META-INF/com/google/android/update-binary"

ZIP="$OUT/OneUI51_S901E_XXV_hybrid_debloat.zip"
rm -f "$ZIP"
(
    cd "$STAGE"
    zip -r0 "$ZIP" \
        META-INF dynamic_partitions_op_list unsparse_super_empty.img debloat.txt \
        ./*.new.dat.br ./*.transfer.list ./*.patch.dat \
        boot.img dtbo.img vendor_boot.img vbmeta.img vbmeta_system.img
)
sha256sum "$ZIP" | tee "$ZIP.sha256"
echo "BUILD_OK $ZIP"
