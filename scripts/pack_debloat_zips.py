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
    /dev/block/mapper/userdata
  do
    if [ ! -e "$dev" ]; then
      continue
    fi
    blockdev --setrw "$dev" 2>/dev/null
    mount -t f2fs -o rw,noatime "$dev" /data 2>/dev/null && return 0
    mount -o rw,noatime "$dev" /data 2>/dev/null && return 0
  done
  return 1
}
wipe_data() {
  if ! mount_data; then
    log "userdata not mounted"
    echo x >> /tmp/hsui_debloat_fail
    return 1
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


def main():
    extra_system = [
        "priv-app/Bixby",
        "app/BixbyWakeup",
        "priv-app/BixbyVisionFramework3.5",
        "priv-app/SettingsBixby",
        "app/VisionIntelligence3.7",
        "priv-app/SVoiceIME",
        "priv-app/BsdService",
        "priv-app/SohService",
        "priv-app/Finder",
        "priv-app/SVCAgent",
        "priv-app/YourPhone_P1_5",
        "priv-app/GameTools_Dream",
        "priv-app/GameOptimizingService",
        "app/ARZone",
        "priv-app/AREmoji",
        "priv-app/AREmojiEditor",
        "app/ARDrawing",
        "priv-app/SmartTouchCall",
        "priv-app/AvatarEmojiSticker",
        "priv-app/StickerFaceARAvatar",
        "app/StickerCenter",
        "app/MinusOnePage",
        "priv-app/ThemeStore",
        "priv-app/GalaxyApps_OPEN",
        "priv-app/SamsungBilling",
        "app/KidsHome_Installer",
        "app/GearManagerStub",
        "app/DictDiotekForSec",
        "priv-app/GpuWatchApp",
        "app/SmartSwitchAgent",
        "priv-app/SmartSwitchAssistant",
        "priv-app/SamsungCloudClient",
        "priv-app/DigitalWellbeing",
        "priv-app/LinkToWindowsService",
    ]
    extra_prism = [
        "app/SwiftKey-market-arm64-v8a-release",
        "app/SwiftKeyFactorySettings-samsung",
    ]
    extra_pkgs = [
        "com.samsung.android.bixby.agent",
        "com.samsung.android.bixby.wakeup",
        "com.samsung.android.bixbyvision.framework",
        "com.samsung.android.app.settings.bixby",
        "com.samsung.android.visionintelligence",
        "com.samsung.android.svoiceime",
        "com.samsung.sait.bsdservice",
        "com.samsung.sait.sohservice",
        "com.samsung.android.app.galaxyfinder",
        "com.samsung.android.svcagent",
        "com.microsoft.appmanager",
        "com.samsung.android.game.gametools",
        "com.samsung.android.game.gos",
        "com.samsung.android.arzone",
        "com.samsung.android.aremoji",
        "com.samsung.android.aremojieditor",
        "com.samsung.android.ardrawing",
        "com.samsung.android.visualars",
        "com.sec.android.mimage.avatarstickers",
        "com.samsung.android.app.camera.sticker.facearavatar.preload",
        "com.samsung.android.stickercenter",
        "com.samsung.android.app.spage",
        "com.samsung.android.themestore",
        "com.sec.android.app.samsungapps",
        "com.sec.android.app.billing",
        "com.samsung.android.kidsinstaller",
        "com.samsung.android.app.watchmanagerstub",
        "com.diotek.sec.lookup.dictionary",
        "com.samsung.gpuwatchapp",
        "com.sec.android.easyMover",
        "com.sec.android.easyMover.Agent",
        "com.samsung.android.smartswitchassistant",
        "com.touchtype.swiftkey",
        "com.swiftkey.swiftkeyconfigurator",
        "com.samsung.android.scloud",
        "com.samsung.android.forest",
        "com.samsung.android.mdx",
        "com.samsung.android.app.tips",
    ]
    rest_system = [
        "app/EasterEgg",
        "app/BasicDreams",
        "app/PhotoTable",
        "app/VoiceAccess",
        "app/LiveTranscribe",
        "priv-app/OmaCP",
        "priv-app/AppUpdateCenter",
        "priv-app/serviceModeApp_FB",
        "priv-app/HwModuleTest",
        "app/Cameralyzer",
        "app/TetheringAutomation",
        "priv-app/BuiltInPrintService",
        "app/PrintSpooler",
        "app/GooglePrintRecommendationService",
    ]
    rest_product = [
        "priv-app/Velvet",
        "priv-app/Turbo",
        "priv-app/AndroidAutoStub",
        "priv-app/FamilyLinkParentalControls",
        "priv-app/AndroidSystemIntelligence",
        "priv-app/PrivateComputeServices",
    ]
    rest_prism = extra_prism
    rest_pkgs = [
        "com.android.egg",
        "com.android.dreams.basic",
        "com.android.dreams.phototable",
        "com.google.android.googlequicksearchbox",
        "com.google.android.apps.turbo",
        "com.google.android.apps.accessibility.voiceaccess",
        "com.google.audio.hearing.visualization.accessibility.scribe",
        "com.google.android.projection.gearhead",
        "com.wsomacp",
        "com.samsung.android.app.updatecenter",
        "com.sec.android.app.servicemodeapp",
        "com.sec.android.app.hwmoduletest",
        "com.sec.factory.cameralyzer",
        "com.sec.automation",
        "com.touchtype.swiftkey",
        "com.swiftkey.swiftkeyconfigurator",
        "com.android.bips",
        "com.android.printspooler",
        "com.google.android.printservice.recommendation",
        "com.google.android.gms.supervision",
        "com.google.android.as",
        "com.google.android.as.oss",
    ]
    extra_body = f"""
open_part system f2fs || exit 1
SYS=$(app_root "$RESULT") || exit 1
log "system $SYS"
wipe_tree "$SYS" "" {words(extra_system)}
open_part prism ext4 || exit 1
PRISM=$(app_root "$RESULT") || exit 1
log "prism $PRISM"
wipe_tree "$PRISM" "prism " {words(extra_prism)}
wipe_data {words(extra_pkgs)}
"""
    rest_body = f"""
open_part system f2fs || exit 1
SYS=$(app_root "$RESULT") || exit 1
log "system $SYS"
wipe_tree "$SYS" "" {words(rest_system)}
open_part product f2fs || exit 1
PROD=$(app_root "$RESULT") || exit 1
log "product $PROD"
wipe_tree "$PROD" "product " {words(rest_product)}
open_part prism ext4 || exit 1
PRISM=$(app_root "$RESULT") || exit 1
log "prism $PRISM"
wipe_tree "$PRISM" "prism " {words(rest_prism)}
wipe_data {words(rest_pkgs)}
"""
    extra_updater = """ui_print("Extra Samsung packages");
ui_print("Does not touch calls, account, camera, Wi-Fi Calling or DressRoom");
package_extract_dir("extra", "/tmp/extra");
run_program("/sbin/sh", "/tmp/extra/apply.sh");
ui_print("Done");
"""
    rest_updater = """ui_print("Remove leftover debloat packages");
ui_print("system, product and prism");
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
