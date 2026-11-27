#!/usr/bin/env python3
"""Pack the OrangeFox debloat zips.

The old scripts deleted nothing that stuck. OrangeFox mounts system
read-only, so rm failed and the script still printed "removed" and
exited 0. Prism is a separate ext4 partition and was never mounted.
Product was picked from an empty /system_root/product directory.
"""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPDATER = os.path.join(ROOT, "prebuilts", "updater")
OUT_DIR = os.path.join(ROOT, "recovery")

SHELL = r"""#!/sbin/sh
LOG=__LOG__
: > "$LOG"
log() {
  echo "$1"
  echo "$1" >> "$LOG"
}
canon() {
  out=$(readlink -f "$1" 2>/dev/null) || out=""
  if [ -n "$out" ]; then
    echo "$out"
  else
    echo "$1"
  fi
}
open_part() {
  name="$1"
  fstype="$2"
  RESULT=""
  dev=""
  for cand in \
    /dev/block/mapper/$name \
    /dev/block/by-name/$name \
    /dev/block/bootdevice/by-name/$name \
    /dev/block/platform/soc/1d84000.ufshc/by-name/$name
  do
    if [ -e "$cand" ]; then
      dev="$cand"
      break
    fi
  done
  if [ -z "$dev" ]; then
    log "no device $name"
    return 1
  fi
  blockdev --setrw "$dev" 2>/dev/null
  mp=""
  want=$(canon "$dev")
  while read -r src dst _rest; do
    case "$src" in
      /dev/*) ;;
      *) continue ;;
    esac
    got=$(canon "$src")
    if [ "$got" = "$want" ] || [ "$src" = "$dev" ]; then
      mp="$dst"
      break
    fi
  done < /proc/mounts
  if [ -n "$mp" ]; then
    mount -o remount,rw "$mp" 2>/dev/null
    if touch "$mp/.hsui_rw" 2>/dev/null; then
      rm -f "$mp/.hsui_rw"
      RESULT="$mp"
      log "$name rw $mp"
      return 0
    fi
    log "remount failed $name"
    umount "$mp" 2>/dev/null || umount -l "$mp" 2>/dev/null
  fi
  mnt="/mnt/$name"
  mkdir -p "$mnt"
  if [ "$fstype" = "ext4" ]; then
    mount -t ext4 -o rw,noatime "$dev" "$mnt" 2>/dev/null \
      || mount -o rw,noatime "$dev" "$mnt" 2>/dev/null \
      || { log "mount failed $name"; return 1; }
  else
    mount -t f2fs -o rw,noatime "$dev" "$mnt" 2>/dev/null \
      || mount -o rw,noatime "$dev" "$mnt" 2>/dev/null \
      || { log "mount failed $name"; return 1; }
  fi
  if touch "$mnt/.hsui_rw" 2>/dev/null; then
    rm -f "$mnt/.hsui_rw"
    RESULT="$mnt"
    log "$name rw $mnt"
    return 0
  fi
  log "still read-only $name"
  return 1
}
app_root() {
  base="$1"
  if [ -d "$base/system/priv-app" ] || [ -d "$base/system/app" ]; then
    echo "$base/system"
    return 0
  fi
  if [ -d "$base/priv-app" ] || [ -d "$base/app" ]; then
    echo "$base"
    return 0
  fi
  log "empty filesystem $base"
  return 1
}
wipe_tree() {
  root="$1"
  tag="$2"
  shift 2
  for rel in "$@"; do
    target="$root/$rel"
    if [ ! -e "$target" ] && [ ! -L "$target" ]; then
      log "absent $tag$rel"
      continue
    fi
    rm -rf "$target"
    if [ -e "$target" ] || [ -L "$target" ]; then
      log "failed $tag$rel"
      echo x >> /tmp/hsui_debloat_fail
    else
      log "removed $tag$rel"
    fi
  done
}
mount_data() {
  if grep -q ' /data ' /proc/mounts; then
    return 0
  fi
  mkdir -p /data
  for dev in \
    /dev/block/by-name/userdata \
    /dev/block/bootdevice/by-name/userdata \
    /dev/block/mapper/userdata \
    /dev/block/platform/soc/1d84000.ufshc/by-name/userdata
  do
    if [ ! -e "$dev" ]; then
      continue
    fi
    blockdev --setrw "$dev" 2>/dev/null
    # Plain f2fs only — flash this zip after Format Data and before first boot,
    # while userdata is still unencrypted.
    mount -t f2fs -o rw,noatime "$dev" /data 2>/dev/null && return 0
    mount -o rw,noatime "$dev" /data 2>/dev/null && return 0
  done
  return 1
}
wipe_data() {
  # After Format Data, /data is empty; mounting may still fail if FBE already
  # started. System/product/prism removals are what matter — do not fail the zip.
  if ! mount_data; then
    log "userdata not mounted (ok after format / before first boot)"
    return 0
  fi
  find /data/app -mindepth 2 -maxdepth 3 -type d > /tmp/hsui_applist 2>/dev/null || true
  while read -r dir; do
    [ -n "$dir" ] || continue
    base=${dir##*/}
    for pkg in "$@"; do
      case "$base" in
        "$pkg"|"$pkg"-*)
          rm -rf "$dir"
          if [ -e "$dir" ]; then
            log "failed data $pkg"
            echo x >> /tmp/hsui_debloat_fail
          else
            log "data $pkg"
          fi
          ;;
      esac
    done
  done < /tmp/hsui_applist
  for pkg in "$@"; do
    rm -rf "/data/data/$pkg" "/data/user/0/$pkg" "/data/user_de/0/$pkg"
    if [ -e "/data/data/$pkg" ] || [ -e "/data/user/0/$pkg" ] || [ -e "/data/user_de/0/$pkg" ]; then
      log "failed data $pkg"
      echo x >> /tmp/hsui_debloat_fail
    fi
  done
}

export PATH="/sbin:/system/bin:${PATH}"
rm -f /tmp/hsui_debloat_fail
__BODY__
sync
if [ -s /tmp/hsui_debloat_fail ]; then
  log "__LABEL__ failed"
  exit 1
fi
log "__LABEL__ ok"
exit 0
"""


def words(items):
    for item in items:
        if any(ch.isspace() for ch in item) or item.startswith("-"):
            raise SystemExit(f"unsafe path {item}")
    return " ".join(items)


def build_script(label, log_path, body):
    text = (
        SHELL.replace("__LOG__", log_path)
        .replace("__LABEL__", label)
        .replace("__BODY__", body)
        .replace("\r\n", "\n")
    )
    if "DressRoom" in text or "dressroom" in text:
        raise SystemExit("DressRoom must stay")
    if "remount,rw" not in text or "blockdev --setrw" not in text:
        raise SystemExit("mount logic missing")
    return text


def pack(name, script_dir, script, updater):
    dest = os.path.join(OUT_DIR, name)
    if os.path.exists(dest):
        os.remove(dest)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.write(UPDATER, "META-INF/com/google/android/update-binary")
        zf.writestr("META-INF/com/google/android/updater-script", updater.replace("\r\n", "\n"))
        zf.writestr(f"{script_dir}/apply.sh", script)
    print("zip", dest, os.path.getsize(dest))


def load_debloat(path):
    groups = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            part, rel = line.split(None, 1)
            groups.setdefault(part, []).append(rel)
    return groups


def body_for(title, groups, mounts):
    lines = [f'log "{title}"']
    for part, fstype, var, tag in mounts:
        rels = groups.get(part, [])
        if not rels:
            continue
        lines.append(f"open_part {part} {fstype} || exit 1")
        lines.append(f'{var}=$(app_root "$RESULT") || exit 1')
        lines.append(f'log "{part} ${var}"')
        lines.append(f'wipe_tree "${var}" "{tag}" {words(rels)}')
    data = groups.get("data", [])
    if data:
        lines.append(f"wipe_data {words(data)}")
    return "\n".join(lines) + "\n"


def main():
    # Optional zips. The ROM image uses un1ca_debloat.list, not these files.
    # Kept out: Wi-Fi Calling, OMC, SDM, fingerprint touch, Find My Mobile,
    # SOS, SIM toolkit, DocumentsUI, Routines, Secure Folder, DeX on PC,
    # KLMSAgent, RCS settings.
    lists = os.path.join(ROOT, "target", "r0q")
    extra = load_debloat(os.path.join(lists, "extra_debloat.list"))
    rest = load_debloat(os.path.join(lists, "rest_debloat.list"))
    extra_body = body_for(
        "flash after ROM + Format Data, before first boot",
        extra,
        (
            ("system", "f2fs", "SYS", ""),
            ("prism", "ext4", "PRISM", "prism "),
        ),
    )
    rest_body = body_for(
        "flash after ROM + Format Data, before first boot",
        rest,
        (
            ("system", "f2fs", "SYS", ""),
            ("product", "f2fs", "PROD", "product "),
        ),
    )
    extra_updater = """ui_print("Extra Samsung debloat");
ui_print("Flash after Format Data, before first boot");
ui_print("Bixby, AR, Galaxy Store, themes, games, Smart Switch, cloud");
ui_print("Keeps calls, WFC, OMC, SDM, fingerprint, FMM, Routines, DeX, SOS");
package_extract_dir("extra", "/tmp/extra");
run_program("/sbin/sh", "/tmp/extra/apply.sh");
ui_print("Done");
"""
    rest_updater = """ui_print("Rest debloat");
ui_print("Flash after Format Data, before first boot");
ui_print("Assistant, Android Auto, Family Link, Voice Access, Live Transcribe");
ui_print("Keeps SIM toolkit and DocumentsUI");
package_extract_dir("rest", "/tmp/rest");
run_program("/sbin/sh", "/tmp/rest/apply.sh");
ui_print("Done");
"""
    pack(
        "extra_samsung_S901E.zip",
        "extra",
        build_script("extra samsung", "/tmp/extra_debloat.log", extra_body),
        extra_updater,
    )
    pack(
        "rest_debloat_S901E.zip",
        "rest",
        build_script("rest debloat", "/tmp/rest_debloat.log", rest_body),
        rest_updater,
    )


if __name__ == "__main__":
    main()
