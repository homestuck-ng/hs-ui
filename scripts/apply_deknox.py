#!/usr/bin/env python3
"""Apply UN1CA-style deknox to the One UI 5.1 system/vendor trees.

Sixteen's giant smali patches target One UI 8. This port keeps the
KnoxGuard disable, props, and feature-flag flips that exist on One UI
5.1. The A73 donor libepm is not in this firmware set, so stock libepm
stays and the libraries it links stay with it.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import zipfile

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from smali_tools import assemble, disassemble, tool_paths

# Relative to system/system or system/ (system-as-root layouts both work).
# Stock libepm.so is BIND_NOW and NEEDED by /system/bin/vold. It links
# libsdp_sdk.so and libdualdar.so; libsdp_sdk.so links libsdp_crypto.so.
# libdualdar.so also links libkeyutils.so and libpersona.so, and libepm
# links libknox_filemanager.so. Deleting any of those makes the linker
# fail before main and init reboots with reboot,vold-failed.
# Daemons (dualdard, sdp_cryptod) stay deleted.
DELETE_REL = [
    "app/BlockchainBasicKit",
    "bin/dualdard",
    "bin/sdp_cryptod",
    "etc/init/dualdard.rc",
    "etc/init/kpp.init.rc",
    "etc/init/kss.init.rc",
    "etc/init/sdp_cryptod.rc",
    "etc/permissions/privapp-permissions-com.samsung.android.hdmapp.xml",
    "etc/permissions/privapp-permissions-com.samsung.android.kgclient.xml",
    "etc/permissions/privapp-permissions-com.samsung.android.knox.kfbp.xml",
    "etc/permissions/privapp-permissions-com.samsung.android.knox.knnr.xml",
    "etc/permissions/privapp-permissions-com.samsung.android.knox.mpos.xml",
    "etc/permissions/privapp-permissions-com.samsung.android.knox.pushmanager.xml",
    "etc/permissions/privapp-permissions-com.samsung.android.knox.sandbox.xml",
    "etc/permissions/privapp-permissions-com.samsung.android.knox.zt.framework.xml",
    "etc/permissions/signature-permissions-com.samsung.android.kgclient.xml",
    "etc/sysconfig/preinstalled-packages-com.samsung.android.coldwalletservice.xml",
    "framework/service-samsung-blockchain.jar",
    "lib/android.hardware.weaver@1.0.so",
    "lib/hidl_comm_ddar_client.so",
    "lib/hidl_tlc_blockchain_comm_client.so",
    "lib/libhermes_cred.so",
    "lib/libmdfpp_req.so",
    "lib/libsdp_kekm.so",
    "lib/libtlc_blockchain_comm.so",
    "lib/libtlc_blockchain_direct_comm.so",
    "lib/libtlc_blockchain_keystore.so",
    "lib/vendor.samsung.hardware.tlc.blockchain@1.0.so",
    "lib/vendor.samsung.hardware.tlc.ddar@1.0.so",
    "lib64/android.hardware.weaver@1.0.so",
    "lib64/hidl_comm_ddar_client.so",
    "lib64/hidl_tlc_blockchain_comm_client.so",
    "lib64/libmdfpp_req.so",
    "lib64/libsdp_kekm.so",
    "lib64/libtlc_blockchain_comm.so",
    "lib64/libtlc_blockchain_direct_comm.so",
    "lib64/libtlc_blockchain_keystore.so",
    "lib64/vendor.samsung.hardware.tlc.blockchain@1.0.so",
    "lib64/vendor.samsung.hardware.tlc.ddar@1.0.so",
    "priv-app/HdmApk",
    "priv-app/KnoxAIFrameworkApp",
    "priv-app/KnoxFrameBufferProvider",
    "priv-app/KnoxGuard",
    "priv-app/KnoxMposAgent",
    "priv-app/KnoxNeuralNetworkRuntime",
    "priv-app/KnoxPushManager",
    "priv-app/KnoxSandbox",
    "priv-app/KnoxZtFramework",
]

SYSTEM_PROPS = {
    "security.mdf.result": "",
    "security.mdf": "",
    "ro.security.mdf.ver": "",
    "ro.security.mdf.release": "",
    "ro.security.wlan.ver": "",
    "ro.security.wlan.release": "",
    "ro.security.bt.ver": "",
    "ro.security.bt.release": "",
    "ro.security.bio.ver": "",
    "ro.security.bio.release": "",
    "ro.security.mdf.ux": "",
    "ro.security.fips.ux": "Disabled",
    "ro.security.fips_bssl.ver": "",
    "ro.config.dmverity": "N",
    "ro.security.ai.privacy": "",
}

VENDOR_PROPS = {
    "ro.security.fips_skc.ver": "",
    "ro.security.fips_scrypto.ver": "",
    "ro.security.fips.ux": "Disabled",
}

FLAG_FALSE = [
    "KNOX_SUPPORT_DAR_DUAL",
    "KNOX_SUPPORT_DAR_DUAL_DO",
    "KNOX_SUPPORT_DAR_SDP",
    "KNOX_SUPPORT_DAR_SDP_OR_DUAL",
    "KNOX_SUPPORT_DAR_VIRTUAL_USER",
    "SEC_PRODUCT_FEATURE_KNOX_SUPPORT_DUAL_DAR",
    "SUPPORT_KNOX_SDP_SQLITE",
    "mIsSdpSupported",
    "SERVICE_SAMSUNG_BLOCKCHAIN",
]

RETURN_FALSE = [
    "isBldpEventSupported()Z",
    "isMposSupported()Z",
    "isSupportKGOnSEC()Z",
    "isMdfApplied()Z",
    "isMdfDisabled()Z",
    "isMdfEnabled()Z",
    "isMdfEnforced()Z",
    "isMdfReady()Z",
    "isMdfSupported()Z",
]

KG_CTOR = """.method public constructor <init>(Landroid/content/Context;)V
    .locals 0

    invoke-direct {p0}, Lcom/samsung/android/knoxguard/IKnoxGuardManager$Stub;-><init>()V

    const/4 p1, 0x0

    iput-object p1, p0, Lcom/samsung/android/knoxguard/service/KnoxGuardSeService;->mConnectivityManagerService:Landroid/net/ConnectivityManager;

    new-instance p0, Ljava/lang/UnsupportedOperationException;

    const-string p1, "KnoxGuard is unsupported"

    invoke-direct {p0, p1}, Ljava/lang/UnsupportedOperationException;-><init>(Ljava/lang/String;)V

    throw p0
.end method
"""


def system_root(tree_system: str) -> str:
    nested = os.path.join(tree_system, "system")
    if os.path.isdir(os.path.join(nested, "framework")):
        return nested
    return tree_system


def delete_paths(sysroot: str) -> list[str]:
    removed = []
    for rel in DELETE_REL:
        path = os.path.join(sysroot, rel.replace("/", os.sep))
        if os.path.exists(path) or os.path.islink(path):
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed.append(rel)
            print("DEL", rel)
    return removed


def set_props(root: str, mapping: dict[str, str]) -> None:
    for dirpath, _, files in os.walk(root):
        if "build.prop" not in files:
            continue
        path = os.path.join(dirpath, "build.prop")
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
        keys = set(mapping)
        out = []
        seen = set()
        for line in lines:
            if not line or line.startswith("#") or "=" not in line:
                out.append(line)
                continue
            key = line.split("=", 1)[0]
            if key in keys:
                out.append(f"{key}={mapping[key]}")
                seen.add(key)
            else:
                out.append(line)
        for key, value in mapping.items():
            if key not in seen:
                out.append(f"{key}={value}")
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out) + "\n")
        print("props", path)


def flip_flags(text: str) -> tuple[str, int]:
    count = 0
    for name in FLAG_FALSE:
        pattern = re.compile(
            rf"(\.field[^\n]*\b{re.escape(name)}\b[^\n]*=\s*)true\b"
        )
        text, n = pattern.subn(r"\1false", text)
        count += n
    return text, count


def force_return_false(text: str, method_sig: str) -> tuple[str, bool]:
    token = f".method public static {method_sig}"
    alt = f".method public {method_sig}"
    greylist = f".method public greylist {method_sig}"
    blacklist = f".method public blacklist {method_sig}"
    start = -1
    for cand in (token, alt, greylist, blacklist, f".method public static blacklist {method_sig}", f".method public static greylist {method_sig}"):
        start = text.find(cand)
        if start >= 0:
            break
    if start < 0:
        # native methods: turn into plain false returns when possible
        native = f".method public static native {method_sig}"
        if native in text:
            text = text.replace(
                native + "\n.end method",
                f".method public static {method_sig}\n    .locals 1\n\n    const/4 v0, 0x0\n\n    return v0\n.end method",
                1,
            )
            return text, True
        return text, False
    end = text.find(".end method", start)
    if end < 0:
        return text, False
    end += len(".end method")
    stub = (
        f".method public static {method_sig}\n"
        if " static " in text[start:start + 40]
        else f".method public {method_sig}\n"
    )
    # Keep the original method declaration line.
    decl = text[start:text.find("\n", start)]
    body = f"{decl}\n    .locals 1\n\n    const/4 v0, 0x0\n\n    return v0\n.end method"
    return text[:start] + body + text[end:], True


def disable_knoxguard(text: str, path: str) -> tuple[str, bool]:
    if path.endswith("KnoxGuardSeService.smali") or path.replace("\\", "/").endswith(
        "knoxguard/service/KnoxGuardSeService.smali"
    ):
        start = text.find(".method public constructor <init>(Landroid/content/Context;)V")
        if start < 0:
            return text, False
        end = text.find(".end method", start)
        if end < 0:
            return text, False
        end += len(".end method")
        return text[:start] + KG_CTOR.strip() + text[end:], True
    if path.endswith("Utils.smali") and "knoxguard" in path.replace("\\", "/"):
        updated, ok = force_return_false(text, "isSupportKGOnSEC()Z")
        return updated, ok
    return text, False


def patch_smali_tree(smali_dir: str) -> dict[str, int]:
    stats = {"flags": 0, "returns": 0, "knoxguard": 0}
    for dirpath, _, files in os.walk(smali_dir):
        for name in files:
            if not name.endswith(".smali"):
                continue
            path = os.path.join(dirpath, name)
            original = open(path, encoding="utf-8").read()
            text = original
            text, n = flip_flags(text)
            stats["flags"] += n
            for sig in RETURN_FALSE:
                text, ok = force_return_false(text, sig)
                if ok:
                    stats["returns"] += 1
            text, ok = disable_knoxguard(text, path)
            if ok:
                stats["knoxguard"] += 1
            if text != original:
                open(path, "w", encoding="utf-8", newline="\n").write(text)
    return stats


def dex_may_need_patch(dex_path: str) -> bool:
    """Skip dexes that cannot contain our targets (string table sniff)."""
    data = open(dex_path, "rb").read()
    needles = (
        b"KnoxGuardSeService",
        b"isSupportKGOnSEC",
        b"KNOX_SUPPORT_DAR",
        b"SERVICE_SAMSUNG_BLOCKCHAIN",
        b"isMdfEnabled",
        b"isMposSupported",
        b"mIsSdpSupported",
        b"SUPPORT_KNOX_SDP",
    )
    return any(n in data for n in needles)


def rewrite_jar(jar_path: str, tool_dir: str) -> dict[str, int]:
    baksmali, smali = tool_paths(tool_dir)
    with zipfile.ZipFile(jar_path) as archive:
        dexes = [n for n in archive.namelist() if n.startswith("classes") and n.endswith(".dex")]
    if not dexes:
        raise SystemExit("no dex in " + jar_path)
    totals = {"flags": 0, "returns": 0, "knoxguard": 0}
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(jar_path) as archive:
            archive.extractall(tmp, dexes)
        changed_dexes = []
        for dex in dexes:
            dex_path = os.path.join(tmp, dex)
            if not dex_may_need_patch(dex_path):
                continue
            out = os.path.join(tmp, dex + ".out")
            disassemble(baksmali, dex_path, out)
            stats = patch_smali_tree(out)
            if any(stats.values()):
                assemble(smali, out, dex_path)
                changed_dexes.append(dex)
                for k, v in stats.items():
                    totals[k] += v
                print("deknox", os.path.basename(jar_path), dex, stats)
        if not changed_dexes:
            print("deknox no smali hits in", jar_path)
            return totals
        tmp_jar = jar_path + ".tmp"
        with zipfile.ZipFile(jar_path, "r") as src, zipfile.ZipFile(tmp_jar, "w") as dst:
            for info in src.infolist():
                if info.filename in changed_dexes:
                    data = open(os.path.join(tmp, info.filename), "rb").read()
                else:
                    data = src.read(info.filename)
                dst.writestr(info, data)
        os.replace(tmp_jar, jar_path)
    return totals


def find_jar(root: str, name: str) -> str | None:
    for dirpath, _, files in os.walk(root):
        if name in files and "framework" in dirpath.replace("\\", "/"):
            return os.path.join(dirpath, name)
    return None


def nuke_floating_blockchain(sysroot: str) -> None:
    for dirpath, _, files in os.walk(sysroot):
        if "floating_feature.xml" not in files:
            continue
        path = os.path.join(dirpath, "floating_feature.xml")
        text = open(path, encoding="utf-8", errors="replace").read()
        new = re.sub(
            r"<SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_BLOCKCHAIN_SERVICE>.*?</SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_BLOCKCHAIN_SERVICE>",
            "",
            text,
            flags=re.S,
        )
        new = new.replace(
            "<SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_BLOCKCHAIN_SERVICE>TRUE</SEC_FLOATING_FEATURE_FRAMEWORK_SUPPORT_BLOCKCHAIN_SERVICE>",
            "",
        )
        if new != text:
            open(path, "w", encoding="utf-8", newline="\n").write(new)
            print("floating", path)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: apply_deknox.py TREE")
    tree = sys.argv[1]
    system = os.path.join(tree, "system")
    vendor = os.path.join(tree, "vendor")
    if not os.path.isdir(system):
        raise SystemExit("missing system tree " + system)
    sysroot = system_root(system)
    removed = delete_paths(sysroot)
    set_props(system, SYSTEM_PROPS)
    if os.path.isdir(vendor):
        set_props(vendor, VENDOR_PROPS)
    nuke_floating_blockchain(sysroot)
    tool_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prebuilts", "smali")
    totals = {"flags": 0, "returns": 0, "knoxguard": 0}
    for name in ("framework.jar", "services.jar", "knoxsdk.jar"):
        jar = find_jar(sysroot, name)
        if jar is None:
            print("skip missing", name)
            continue
        stats = rewrite_jar(jar, tool_dir)
        for k, v in stats.items():
            totals[k] += v
    if totals["knoxguard"] < 1 and not any(r.endswith("KnoxGuard") for r in removed):
        raise SystemExit("KnoxGuard was not disabled")
    # Package may remain as an empty priv-app dir after delete; ensure apk gone.
    kg = os.path.join(sysroot, "priv-app", "KnoxGuard")
    if os.path.isdir(kg):
        raise SystemExit("KnoxGuard directory still present")
    print(
        "deknox ok",
        "removed",
        len(removed),
        "flags",
        totals["flags"],
        "returns",
        totals["returns"],
        "knoxguard",
        totals["knoxguard"],
    )


if __name__ == "__main__":
    main()
