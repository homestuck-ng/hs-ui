# HS-UI 5.1

![HS-UI 5.1](docs/hs-ui-5.1.jpg)

One UI 5.1 for the Galaxy S22, SM-S901E (r0q, XXV), on a binary C bootloader.
# Our chat: [Telegram Chat](https://t.me/+40RGROGV-2IzZWRi)

Debloat, Knox removal, and the r0q file lists come from [UN1CA](https://github.com/salvogiangreco/UN1CA). The Bluetooth patch comes from [BluetoothLibraryPatcher](https://github.com/3arthur6/BluetoothLibraryPatcher).

| Part | Source |
| --- | --- |
| system, vendor, product, system_ext, odm | One UI 5.1 `S901EXXS7CWI1` |
| boot, dtbo, vendor_boot, vendor_dlkm | One UI 6.1 `S901EXXSCEYB1` |

Do not flash BL or CP from this ROM. Do not use a base newer than binary C. `S901EXXSEGZH4` is binary G.

## Install

### 1. Base

The phone must already be on One UI 6.1 binary C, `S901EXXSCEYB1`, region XXV.

[SM-S901E XXV S901EXXSCEYB1 on SamFW](https://samfw.com/firmware/SM-S901E/XXV/S901EXXSCEYB1)

Odin: BL, AP, CP, HOME_CSC. HOME_CSC keeps data. CSC erases it. Re-Partition off. Skip this step if Software information already shows `S901EXXSCEYB1`.

### 2. Recovery (FBE decrypt fork)

Files are in `recovery/`. The OrangeFox here is built from [homestuck-ng/android_device_samsung_r0q_twrp](https://github.com/homestuck-ng/android_device_samsung_r0q_twrp) (`fox_12.1`, also mirrored under `external/orangefox_device_samsung_r0q`). That fork turns on QCOM FBE decrypt and points `/data` at Samsung metadata encryption so OrangeFox can unlock with the **Android lockscreen PIN / password / pattern**.

| File | Role |
| --- | --- |
| `OrangeFox-R12.0_A12-Unofficial-r0q.img.tar` | OrangeFox for Odin (FBE fork). Rebuild via [OrangeFox](https://github.com/homestuck-ng/hs-ui/actions/workflows/orangefox.yml). |
| `patched-vb.tar` | `vbmeta.img`, flags `00 00 00 03` |

1. Enable OEM unlock. Power off. Hold both volume keys, connect the cable, then press volume up to enter Download mode.
2. Odin: Auto Reboot off, Re-Partition off.
3. AP: the OrangeFox tar. CP: `patched-vb.tar`.
4. Start. Wait for PASS.
5. Do not boot the system. Hold volume down and power until the screen goes off, then immediately hold volume up and power to open OrangeFox. A normal boot restores the stock recovery.
6. When OrangeFox asks for a password, enter the same lockscreen credential used in Android.

### 3. ROM

The flashable file is `OneUI51_S901E_XXV_hybrid.zip`. Download the artifact from the latest successful [Build](https://github.com/homestuck-ng/hs-ui/actions/workflows/build.yml) run. Open it and flash `OneUI51_S901E_XXV_hybrid.zip` in OrangeFox. That zip contains `META-INF`.

This hybrid keeps stock userdata FBE (`fileencryption` + `metadata_encryption` + `keydirectory`). On a first install onto encrypted data that was created by a different policy, **Format Data** in OrangeFox, then set a lockscreen credential after the first Android boot. Dirty flash of the zip itself is fine once the policy already matches.

## What stays

Calls, SMS, camera, gallery, Samsung keyboard, DeX, My Files, Routines, Reminder, location, emergency calls, Find My Mobile, Samsung Account, Play Store, Google services, and Wi-Fi Calling.

## What is removed

The UN1CA r0q debloat list: Chrome, Gmail, Maps, YouTube, Google Messages, Duo, OneDrive, Facebook services, Game Launcher, Samsung Pass, payment and auth frameworks, factory tests, SIM unlock, and Play Auto Install. KnoxGuard and the Knox framework pieces that UN1CA removes in deknox are still removed here.

eSIM, `fabric_crypto`, OMC, and SDM stay.

## Optional zips

Flash order in OrangeFox: **ROM zip → Format Data → `debloat_S901E.zip` → reboot to system** (first boot creates FBE). Do not boot Android between Format Data and the debloat zip. The zip mounts system, product, and prism itself and only soft-skips `/data` if it is not mountable yet.

| Zip | Partitions | Effect |
| --- | --- | --- |
| `recovery/debloat_S901E.zip` | system, prism, product | List: `target/r0q/debloat.list`. Removes Bixby, AR/emoji, Galaxy Store, themes, Game Tools, Smart Switch, SwiftKey market, Samsung Cloud, Digital Wellbeing, Link to Windows, Assistant, Android Auto stub, Family Link, App Update Center, Voice Access, Live Transcribe, BasicDreams/PhotoTable. Leaves Wi-Fi Calling, OMC, SDM, fingerprint, Find My Mobile, SOS, SIM toolkit, DocumentsUI, Routines, Secure Folder, DeX on PC, KLMSAgent, RCS, dialer, messages, camera. Log: `/tmp/debloat.log`. |

The old `encryption_S901E.zip` is gone. Encryption stays in the hybrid ROM (stock vendor + vendor_boot FBE flags). OrangeFox FBE unlock is the [r0q_twrp fork](https://github.com/homestuck-ng/android_device_samsung_r0q_twrp) `fox_12.1`.

## Build

- ROM: Actions → Build → Run workflow. Firmware AP files come from [firmware-v1](https://github.com/homestuck-ng/hs-ui/releases/tag/firmware-v1). BL and CP are not in that release.
- OrangeFox: Actions → OrangeFox → Run workflow. Uses `external/orangefox_device_samsung_r0q` and uploads an Odin tar artifact.
