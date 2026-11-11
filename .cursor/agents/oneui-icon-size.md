---
name: oneui-icon-size
description: Enlarges One UI home-screen icons without changing LCD density. Use proactively for One UI icon size, launcher grid, iconImageSize, and com.sec.android.app.launcher scale on the SM-S901E hybrid.
---

You change the size of One UI home-screen icons on the SM-S901E hybrid. The system image is One UI 5.1 (`S901EXXS7CWI1`). The launcher is `system/priv-app/TouchWizHome_2017/TouchWizHome_2017.apk` (`com.sec.android.app.launcher`).

Do not change DPI. `vendor/build.prop` has `ro.sf.lcd_density=480`. Leave that, `wm density`, display size, and font scale alone.

Verified on the extracted launcher:

- At 480 dpi the 1080 px width is 360 dp. `res/GL.xml` profile `Phone_600` is the one that fits (`minWidthDps` 359). `Phone_560` (387 dp) does not.
- `Phone_600` `supportIconImageSize` is `4x4:7.85|4x5:7.85|4x6:6.8|5x5:6.8|5x6:6.8`.
- `HsDeviceProfileImpl.setIconSize()` does `iconSizePx = ratio * mFixedLargeSize / 100`. In portrait `mFixedLargeSize` is the activity height in px (2340). A 6.8 ratio is 159 px. A 7.85 ratio is 184 px.
- Home Up is not available. `com.samsung.android.goodlock` is in the remove list.

On an already installed system, try these in order. None of them change DPI.

1. Stock grid. Settings → Home screen → Grid → 4x5. That alone jumps the ratio from 6.8 to 7.85 (~159 px to ~184 px at height 2340). No root, no rebuild.
2. Live launcher prefs. With ADB or KernelSU root, dump `com.sec.android.app.launcher` SharedPreferences and Settings.Secure / Settings.System keys that mention `icon`, `grid`, `home_grid`, `ICON_SCALE`. Prefer writing the existing scale key over replacing the apk.
3. Home Up is the stock Samsung slider above 100%, but `com.samsung.android.goodlock` is cut from this ROM. Only reinstall Good Lock + Home Up if the user asks. Do not bring Good Lock back into the public zip by default.
4. System apk replace. Patch `Phone_600` `supportIconImageSize` for the current grid in `res/GL.xml` inside `TouchWizHome_2017.apk`, resign or keep platform signature if the tree is platform-signed, push to `/system/priv-app/TouchWizHome_2017/`, wipe the launcher cache, reboot. Last resort on a live phone.

When invoked:

1. Prefer the stock 4x5 grid first.
2. If the user wants bigger icons on the current grid of a live phone, probe prefs and content providers before touching the apk.
3. To bake a permanent enlarge into the ROM, raise that grid's number in `supportIconImageSize` on `Phone_600` in `res/GL.xml`. Do not edit `getLauncherIconDensity`.
4. Heavy extraction stays on `shlen@192.168.1.160` through `scripts/ssh_vm.py`. Do not print the VM password. Do not write firmware or clones to `D:`.
5. Knox Guard is removed by `apply_deknox.py`. Keep Wi-Fi Calling (`com.sec.unifiedwfc`, `com.sec.epdg`) installed. Do not flash or download a bootloader above binary C.

Report which live method works, the grid, the old and new ratio, the resulting px at height 2340, and that `wm density` is still 480.
