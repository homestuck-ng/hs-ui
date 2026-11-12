#!/usr/bin/env bash
# Build the SM-S901E One UI 5.1 hybrid zip.
# Firmware is fetched with ananjaser1211/samloader, the same tool UN1CA sixteen calls.
set -euo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:${PATH}"

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
    local meta="${3:-}"
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
            if [[ -n "$meta" ]]; then
                python3 "$ROOT/scripts/dump_fs_meta.py" "$dest" "$meta"
            fi
            ;;
        f2fs|ext4)
            local mnt="$WORK/mnt"
            mkdir -p "$mnt"
            sudo umount "$mnt" 2>/dev/null || true
            sudo mount -o ro,loop "$img" "$mnt"
            if [[ -n "$meta" ]]; then
                sudo python3 "$ROOT/scripts/dump_fs_meta.py" "$mnt" "$meta"
            fi
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
mkdir -p "$WORK/meta"
extract_fs "$SYS/parts/system.img" "$TREE/system" "$WORK/meta/system.jsonl"
extract_fs "$SYS/parts/vendor.img" "$TREE/vendor" "$WORK/meta/vendor.jsonl"
extract_fs "$BOOT/parts/vendor_dlkm.img" "$TREE/vendor_dlkm"
# product, system_ext and odm are not patched. Keep the stock f2fs images.
SYSTEM_BYTES=$(stat -c %s "$SYS/parts/system.img")
VENDOR_BYTES=$(stat -c %s "$SYS/parts/vendor.img")
unsparse "$SYS/parts/product.img"
unsparse "$SYS/parts/system_ext.img"
unsparse "$SYS/parts/odm.img"
cp -a "$SYS/parts/product.img" "$WORK/product.img"
cp -a "$SYS/parts/system_ext.img" "$WORK/system_ext.img"
cp -a "$SYS/parts/odm.img" "$WORK/odm.img"
rm -rf "$SYS/parts" "$BOOT/parts"
echo "stock bytes system=$SYSTEM_BYTES vendor=$VENDOR_BYTES"

echo "=== vintf ==="
echo "debloat not applied; deknox and vendor fixes are in the f2fs images" > "$STAGE/debloat.txt"
MAN="$TREE/vendor/etc/vintf/manifest"
rm -f \
    "$MAN/vendor.samsung.hardware.sehradio_manifest_2_31.xml" \
    "$MAN/vendor.samsung.hardware.radio_manifest_2_31.xml" \
    "$MAN/vendor.samsung.hardware.radio.exclude.qcom.xml" \
    "$MAN/iweaver_v1_manifest.xml"
python3 "$ROOT/scripts/vermagic.py" "$TREE/vendor_dlkm"

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

align_seg() {
    python3 -c "n=int('$1'); seg=2*1024*1024; print(((n+seg-1)//seg)*seg)"
}

# sload.f2fs writes the image itself. Mounting a fresh mkfs and copying
# into it returned EIO on the first directory when quota was enabled and
# the file was sized from the uncompressed tree.
mk_f2fs() {
    local label="$1" tree="$2" meta="$3" image="$4" base="$5"
    if [[ -x /usr/local/sbin/sload.f2fs ]]; then
        sload_bin=/usr/local/sbin/sload.f2fs
    else
        sload_bin="$(command -v sload.f2fs)"
    fi
    [[ -n "$sload_bin" ]] || { echo "sload.f2fs missing" >&2; exit 1; }
    sudo python3 "$ROOT/scripts/apply_fs_meta.py" "$tree" "$meta" owners
    local bytes extra
    bytes="$(align_seg "$((base + 64 * 1024 * 1024))")"
    for extra in 0 268435456; do
        bytes="$(align_seg "$((base + 64 * 1024 * 1024 + extra))")"
        echo "sload $label $bytes"
        rm -f "$image"
        truncate -s "$bytes" "$image"
        /usr/sbin/mkfs.f2fs -q -f -O extra_attr,compression -l "$label" -o 8 "$image"
        set +e
        sload_log="$(sudo "$sload_bin" -f "$tree" -t / -P -c -a lz4 -r "$image" 2>&1)"
        sload_rc=$?
        set -e
        printf '%s\n' "$sload_log"
        if [[ "$sload_rc" == 0 && "$sload_log" != *"not supported"* && "$sload_log" != *"Error:"* ]]; then
            break
        fi
        echo "sload $label did not fit in $bytes" >&2
        if [[ "$extra" != 0 ]]; then
            sudo dmesg | tail -n 20 >&2 || true
            exit 1
        fi
    done
    local mnt="$WORK/mnt"
    mkdir -p "$mnt"
    sudo umount "$mnt" 2>/dev/null || true
    if ! sudo mount -t f2fs -o loop "$image" "$mnt"; then
        echo "mount $label failed" >&2
        sudo dmesg | tail -n 40 >&2 || true
        exit 1
    fi
    sudo python3 "$ROOT/scripts/apply_fs_meta.py" "$mnt" "$meta"
    sudo umount "$mnt"
    pad4k "$image"
}

echo "=== framework patches ==="
python3 "$ROOT/scripts/enable_multiuser.py" "$TREE/system"
python3 "$ROOT/scripts/patch_bluetooth_lib.py" "$TREE"
python3 "$ROOT/scripts/apply_deknox.py" "$TREE"

echo "=== userdata stays plain f2fs ==="
python3 "$ROOT/scripts/strip_userdata_encryption.py" "$TREE/vendor"

echo "=== images ==="
pad4k "$WORK/product.img"
pad4k "$WORK/system_ext.img"
mk_f2fs system "$TREE/system" "$WORK/meta/system.jsonl" "$WORK/system.img" "$SYSTEM_BYTES"
sudo rm -rf "$TREE/system"
mk_f2fs vendor "$TREE/vendor" "$WORK/meta/vendor.jsonl" "$WORK/vendor.img" "$VENDOR_BYTES"
sudo rm -rf "$TREE/vendor"

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
sudo chown -R 0:0 "$MNT"
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

ln -sfn "$WORK/system.img" "$STAGE/system.img"
ln -sfn "$WORK/product.img" "$STAGE/product.img"
ln -sfn "$WORK/system_ext.img" "$STAGE/system_ext.img"
ln -sfn "$WORK/vendor.img" "$STAGE/vendor.img"
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
to_dat system "$WORK/system.img"
to_dat product "$WORK/product.img"
to_dat system_ext "$WORK/system_ext.img"
to_dat vendor "$WORK/vendor.img"
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
