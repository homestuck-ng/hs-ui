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
extract_fs "$SYS/parts/product.img" "$TREE/product" "$WORK/meta/product.jsonl"
extract_fs "$SYS/parts/system_ext.img" "$TREE/system_ext" "$WORK/meta/system_ext.jsonl"
extract_fs "$BOOT/parts/vendor_dlkm.img" "$TREE/vendor_dlkm"
# odm has no debloat targets. Keep the stock image.
SYSTEM_BYTES=$(stat -c %s "$SYS/parts/system.img")
VENDOR_BYTES=$(stat -c %s "$SYS/parts/vendor.img")
PRODUCT_BYTES=$(stat -c %s "$SYS/parts/product.img")
SYSTEM_EXT_BYTES=$(stat -c %s "$SYS/parts/system_ext.img")
unsparse "$SYS/parts/odm.img"
cp -a "$SYS/parts/odm.img" "$WORK/odm.img"
rm -rf "$SYS/parts" "$BOOT/parts"
echo "stock bytes system=$SYSTEM_BYTES vendor=$VENDOR_BYTES"

echo "=== vintf ==="
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

# Distro sload exits 1 after a good pack because fsck rewrites SIT.
# The line "Max image size" is the real used size. The first guess is larger
# than the super group, so a successful pack is rebuilt at that size.
mk_f2fs() {
    local label="$1" tree="$2" meta="$3" image="$4" base="$5"
    local logfile="$WORK/meta/sload-$label.log"
    sudo python3 "$ROOT/scripts/apply_fs_meta.py" "$tree" "$meta" owners
    local bytes
    bytes="$(python3 - "$tree" <<'PY'
import os, sys
root = sys.argv[1]
total = 0
files = 0
for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
    for name in dirnames + filenames:
        files += 1
        try:
            total += os.lstat(os.path.join(dirpath, name)).st_size
        except OSError:
            pass
size = total + 256 * 1024 * 1024 + files * 4096
seg = 2 * 1024 * 1024
print(((size + seg - 1) // seg) * seg)
PY
)"
    echo "sload $label tree=$bytes stock=$base"
    try_sload() {
        local this="$1"
        local img="$2"
        local src="$3"
        local logfile="$4"
        local name="$5"
        echo "sload $name $this"
        rm -f "$img"
        truncate -s "$this" "$img"
        /usr/sbin/mkfs.f2fs -q -f -l "$name" -o 1 "$img"
        set +e
        sudo /usr/sbin/sload.f2fs -f "$src" -t / -P "$img" >"$logfile" 2>&1
        local rc=$?
        set -e
        cat "$logfile"
        if [[ "$rc" -le 1 ]] && grep -q "Max image size:" "$logfile"; then
            return 0
        fi
        echo "sload $name failed in $this" >&2
        return 1
    }
    try_sload "$bytes" "$image" "$tree" "$logfile" "$label" \
        || try_sload "$((bytes + 536870912))" "$image" "$tree" "$logfile" "$label" \
        || exit 1
    local mnt="$WORK/mnt"
    mkdir -p "$mnt"
    sudo umount "$mnt" 2>/dev/null || true
    if ! sudo mount -t f2fs -o loop "$image" "$mnt"; then
        echo "mount $label failed" >&2
        sudo dmesg | tail -n 40 >&2 || true
        exit 1
    fi
    sudo python3 "$ROOT/scripts/apply_fs_meta.py" "$mnt" "$meta"
    if [[ "$label" == "system" ]]; then
        sudo python3 - "$mnt" <<'PY'
import os, sys
root = sys.argv[1]
for rel in ("system/lib64/libbluetooth_jni.so", "lib64/libbluetooth_jni.so"):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        continue
    os.chown(path, 0, 0)
    os.chmod(path, 0o644)
    os.setxattr(path, "security.selinux", b"u:object_r:system_lib_file:s0\0")
    print("labeled", rel)
PY
    fi
    sudo umount "$mnt"
    # A second sload into a smaller image crashes. resize.f2fs keeps the
    # packed data and drops the unused tail so the super group still fits.
    local max_mb target current sectors
    max_mb="$(sed -n 's/.*Max image size: \([0-9][0-9]*\) MB.*/\1/p' "$logfile" | tail -n 1)"
    if [[ -n "$max_mb" ]]; then
        target="$(python3 -c "mb=int('$max_mb'); seg=2*1024*1024; size=(mb+128)*1024*1024; print(((size+seg-1)//seg)*seg)")"
        current="$(stat -c %s "$image")"
        if [[ "$target" -lt "$current" ]]; then
            sectors="$((target / 512))"
            echo "resize $label $current -> $target from ${max_mb} MB ($sectors sectors)"
            /usr/sbin/resize.f2fs -t "$sectors" "$image"
            truncate -s "$target" "$image"
        fi
    fi
    pad4k "$image"
}

echo "=== framework patches ==="
echo "debloat mode un1ca"
python3 "$ROOT/scripts/enable_multiuser.py" "$TREE/system"
python3 "$ROOT/scripts/skip_webview32.py" "$TREE/system"
python3 "$ROOT/scripts/patch_bluetooth_lib.py" "$TREE"
: > "$STAGE/debloat.txt"
python3 "$ROOT/scripts/apply_un1ca_debloat.py" "$TREE" \
    "$ROOT/target/r0q/un1ca_debloat.list" "$STAGE/debloat.txt"
python3 "$ROOT/scripts/apply_deknox.py" "$TREE"
python3 - "$STAGE/debloat.txt" "$STAGE/debloat_data.sh" "$STAGE/remove.list" <<'PY'
import sys
log_path, script_path, list_path = sys.argv[1:4]
pkgs = []
seen = set()
for line in open(log_path, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    pkg = line.split()[0]
    if pkg in seen or "." not in pkg:
        continue
    seen.add(pkg)
    pkgs.append(pkg)
open(list_path, "w", encoding="utf-8").write("\n".join(pkgs) + ("\n" if pkgs else ""))
body = """#!/sbin/sh
log() { echo "$1"; }
mount_data() {
  if grep -q ' /data ' /proc/mounts; then
    return 0
  fi
  mkdir -p /data
  for dev in /dev/block/by-name/userdata /dev/block/bootdevice/by-name/userdata /dev/block/mapper/userdata; do
    [ -e "$dev" ] || continue
    blockdev --setrw "$dev" 2>/dev/null
    mount -t f2fs -o rw,noatime "$dev" /data 2>/dev/null && return 0
    mount -o rw,noatime "$dev" /data 2>/dev/null && return 0
  done
  return 1
}
if ! mount_data; then
  log "userdata not mounted"
  exit 1
fi
fail=0
"""
for pkg in pkgs:
    body += f"""
find /data/app -mindepth 2 -maxdepth 3 -type d > /tmp/hsui_applist 2>/dev/null || true
while read -r dir; do
  [ -n "$dir" ] || continue
  base=${{dir##*/}}
  case "$base" in
    "{pkg}"|"{pkg}"-*)
      rm -rf "$dir"
      if [ -e "$dir" ]; then
        log "failed data {pkg}"
        fail=1
      else
        log "data {pkg}"
      fi
      ;;
  esac
done < /tmp/hsui_applist
rm -rf "/data/data/{pkg}" "/data/user/0/{pkg}" "/data/user_de/0/{pkg}"
if [ -e "/data/data/{pkg}" ] || [ -e "/data/user/0/{pkg}" ] || [ -e "/data/user_de/0/{pkg}" ]; then
  log "failed data {pkg}"
  fail=1
fi
"""
body += """
if [ "$fail" -ne 0 ]; then
  log "debloat_data failed"
  exit 1
fi
log "debloat_data ok"
exit 0
"""
open(script_path, "w", newline="\n").write(body)
print("debloat_data", len(pkgs))
PY
chmod 755 "$STAGE/debloat_data.sh"

echo "=== userdata stays plain f2fs ==="
python3 "$ROOT/scripts/strip_userdata_encryption.py" "$TREE/vendor"

echo "=== images ==="
mk_f2fs system "$TREE/system" "$WORK/meta/system.jsonl" "$WORK/system.img" "$SYSTEM_BYTES"
sudo rm -rf "$TREE/system"
mk_f2fs product "$TREE/product" "$WORK/meta/product.jsonl" "$WORK/product.img" "$PRODUCT_BYTES"
sudo rm -rf "$TREE/product"
mk_f2fs system_ext "$TREE/system_ext" "$WORK/meta/system_ext.jsonl" "$WORK/system_ext.img" "$SYSTEM_EXT_BYTES"
sudo rm -rf "$TREE/system_ext"
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

ZIP="$OUT/OneUI51_S901E_XXV_hybrid.zip"
rm -f "$ZIP"
(
    cd "$STAGE"
    zip -r0 "$ZIP" \
        META-INF dynamic_partitions_op_list unsparse_super_empty.img debloat.txt \
        debloat_data.sh remove.list \
        ./*.new.dat.br ./*.transfer.list ./*.patch.dat \
        boot.img dtbo.img vendor_boot.img vbmeta.img vbmeta_system.img
)
sha256sum "$ZIP" | tee "$ZIP.sha256"
echo "BUILD_OK $ZIP"
