# HS-UI 5.1

![HS-UI 5.1](docs/hs-ui-5.1.jpg)

One UI 5.1 for the Galaxy S22, SM-S901E (r0q, XXV), on a binary C bootloader.

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

### 2. Recovery

Files are in `recovery/`.

| File | Role |
| --- | --- |
| `OrangeFox-R12.0_A12-Unofficial-r0q.img.tar` | OrangeFox for Odin. Taken from `OrangeFox-R12.0_A12-Unofficial-r0q.zip`. The full zip is over 100 MB, so GitHub will not store it. |
| `patched-vb.tar` | `vbmeta.img`, flags `00 00 00 03` |

1. Enable OEM unlock. Power off. Hold both volume keys, connect the cable, then press volume up to enter Download mode.
2. Odin: Auto Reboot off, Re-Partition off.
3. AP: the OrangeFox tar. USERDATA: `patched-vb.tar`.
4. Start. Wait for PASS.
5. Do not boot the system. Hold volume down and power until the screen goes off, then immediately hold volume up and power to open OrangeFox. A normal boot restores the stock recovery.

### 3. ROM

Actions, workflow Build. The download is a zip wrapper. Flash the inner `OneUI51_S901E_XXV_hybrid.zip`. It contains `META-INF`. The wrapper will not flash.

Dirty flash is supported. Data is not formatted and is not encrypted. If `/metadata/vold/metadata_encryption` already exists, delete that directory before the first boot.

## What stays

Calls, SMS, camera, gallery, Samsung keyboard, DeX, My Files, Routines, Reminder, location, emergency calls, Find My Mobile, Samsung Account, Play Store, Google services, and Wi-Fi Calling.

## What is removed

The UN1CA r0q list, plus Knox and telemetry: Chrome, Gmail, Maps, YouTube, Google Messages, Duo, OneDrive, Facebook services, Game Launcher, Samsung Pass, payment and auth frameworks, factory tests, SIM unlock, Play Auto Install, Rubin, the agent stack, IMS Logger, Hiya, Knox Guard, KnoxCore, Knox Analytics, KPE, and MDM.

eSIM, `fabric_crypto`, OMC, and SDM stay.

## Optional zips

Flash these in OrangeFox only if you want them. Mount the partition named below first.

| Zip | Mount | Effect |
| --- | --- | --- |
| `recovery/extra_samsung_S901E.zip` | System | Removes Bixby, AR Emoji, Galaxy Store, themes, Game Tools, Smart Switch, SwiftKey, Samsung Cloud, Digital Wellbeing, and Link to Windows. Leaves the dialer, Samsung messages, camera, Samsung Account, Wi-Fi Calling, OMC, and SDM. Log line: `extra samsung`. |
| `recovery/encryption_S901E.zip` | Vendor | Puts `keydirectory` back and encrypts `/data`. Log line: `encryption on`. Do not flash this on a phone whose data is already in use. A later flash of the ROM removes encryption again. |

## Build

Actions, Build, Run workflow. One workflow, no options. Firmware AP files come from [firmware-v1](https://github.com/homestuck-ng/hs-ui/releases/tag/firmware-v1). BL and CP are not in that release.
