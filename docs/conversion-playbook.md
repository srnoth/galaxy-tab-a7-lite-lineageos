# SM-T227U: US firmware to LineageOS GSI

Short version for the LTE Galaxy Tab A7 Lite (`gta7lite` / **SM-T227U**). This replaces Samsung's
system image with a LineageOS 21 GSI, installs TWRP, and unlocks the bootloader with mtkclient. It is
for hardware you own.

> [!WARNING]
> Back up first. A wrong bootloader, preloader, PIT/GPT, or partition write can brick the tablet. This
> guide is only for the **SM-T227U**, and only for Canadian XAC `T227UVLSCFYE2` (bootloader C). Do not
> substitute an older XAC build. This erases the tablet and trips Knox.

## What you need

- Native Linux with a reliable USB-A data port; do not use a VM for BROM work.
- A good USB-A-to-C cable and a charged SM-T227U.
- Full XAC `T227UVLSCFYE2` firmware: BL, AP, CP, and CSC archives. Keep extracted `boot.img`.
- [TWRP v2.2 for gta7lite](https://github.com/gta7lite/teamwin_device_samsung_gta7lite/releases), its
  `fbe_disabler_gta7lite.zip`, and a regular AndyYan LineageOS 21 `arm64_bvN` image. For Google services,
  use the regular `arm64_bgN-signed` image instead. **Do not use vndklite.**
- `mtkclient`, ADB, fastboot, LZ4, `simg2img`, and `magiskboot` (from the official Magisk APK).

Basic Debian/Ubuntu setup:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libusb-1.0-0 lz4 \
  android-tools-adb android-tools-fastboot simg2img
sudo systemctl disable --now ModemManager 2>/dev/null || true
sudo apt -y remove brltty 2>/dev/null || true
git clone https://github.com/bkerler/mtkclient ~/a7lite/mtkclient
cd ~/a7lite/mtkclient
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

For every BROM operation: power the tablet off, unplug it, start the mtkclient command, then hold
**Vol-Up** while connecting USB. A fresh BROM entry is safest for each write. If mtkclient says
`Please disconnect… reconnect`, power off, clear the USB connection, and try again.

## 1. Back up before writing anything

```bash
cd ~/a7lite/mtkclient
./.venv/bin/python mtk.py rl ~/a7lite/backup/rl_all --skip userdata
./.venv/bin/python mtk.py r preloader ~/a7lite/backup/preloader_boot1.bin --parttype boot1
```

Keep that backup off the host. In particular, preserve `lk.bin`, `boot.bin`, `recovery.bin`, `vbmeta.bin`,
and the boot1 preloader dump. Do not proceed if this did not complete.

## 2. Try the normal XAC flash

Enter Samsung Download Mode: power off, hold **Vol-Up + Vol-Down** while connecting USB, then press
**Vol-Up** at the warning screen. With Odin/odin4, flash:

```text
BL  BL_T227UVLSCFYE2_*.tar.md5
AP  AP_T227UVLSCFYE2_*.tar.md5
CP  CP_T227UVLSCFYE2_*.tar.md5
CSC CSC_OYV_T227U*_*.tar.md5
```

Use `CSC`, not `HOME_CSC`; do not enable Re-Partition or NAND Erase. A successful flash boots the XAC
build and offers English (Canada) during setup.

### Verizon fallback: Odin rejects `param`

Some Verizon SM-T227U units reject the full XAC BL before it writes. The observed signature is:

```text
Odin: Re-Partition operation failed
Tablet: Non-KNL image not allowed : param
```

Do not add a PIT or enable Re-Partition. The failure is the XAC BL's `param` image, not a bad cable or a
bad download. The following fallback worked once on a Verizon `T227USQSCEYE2` unit with a complete BROM
backup. It is not a universal guarantee.

Extract the unmodified signed XAC LK, then write **only** that image through BROM:

```bash
cd ~/a7lite/fw
tar -xOf BL_T227UVLSCFYE2_*.tar.md5 lk-verified.img.lz4 > lk-verified.img.lz4
lz4 -d lk-verified.img.lz4 lk-verified.img

cd ~/a7lite/mtkclient
./.venv/bin/python mtk.py w lk ~/a7lite/fw/lk-verified.img
./.venv/bin/python mtk.py da seccfg unlock
```

Do **not** write `preloader`, `param`, `up_param`, `efuse`, the PIT/GPT, or the rest of the XAC BL archive.
After reboot, confirm the tablet actually shows the unlocked-bootloader warning. If it does not, stop. If
you need to undo this experiment, write back your own saved `backup/rl_all/lk.bin` over BROM.

## 3. Unlock and disable verification

On a normal XAC flash, or after the successful LK-only fallback, run the unlock command if it has not
already been run:

```bash
cd ~/a7lite/mtkclient
./.venv/bin/python mtk.py da seccfg unlock
```

The OEM-unlock setting does not appear in Android. A successful unlock forces a wipe and shows the orange
unlocked warning. Only after that warning, enter BROM again and disable AVB verification:

```bash
./.venv/bin/python mtk.py da vbmeta 3
```

## 4. Install and boot TWRP

```bash
cd ~/a7lite/twrp
tar xvf TWRP_v2.2_gta7lite.tar
cd ~/a7lite/mtkclient
./.venv/bin/python mtk.py w recovery ~/a7lite/twrp/recovery.img
```

Do not let stock Android boot after this. Force power off, then hold **Power + Vol-Up**. At the orange
warning, release, tap Power once, then immediately hold **Power + Vol-Up** again. TWRP should appear.

## 5. Flash the GSI

The boot image and GSI must use the same security-patch month or a lock screen PIN will bootloop. Read the
GSI month, patch the boot header, and repack it:

```bash
cd ~/a7lite/fw
grep -a -o 'ro.build.version.security_patch=[0-9-]*' lineage-21.0-*-arm64_bvN.img
./magiskboot unpack -h boot.img
sed -i 's/^os_patch_level=.*/os_patch_level=YYYY-MM/' header
./magiskboot repack boot.img
```

Replace `YYYY-MM` with the month printed by `grep`. For the normal route, `boot.img` is the extracted XAC
boot image. For the Verizon LK-only fallback, use the original US `boot.bin` from your backup as `boot.img`.

In TWRP:

```bash
adb push ~/a7lite/twrp/fbe_disabler_gta7lite.zip /tmp/fbe.zip
adb shell twrp install /tmp/fbe.zip
adb shell twrp format data
adb reboot fastboot
fastboot getvar is-userspace
fastboot erase system
fastboot delete-logical-partition product
fastboot flash system ~/a7lite/fw/lineage-21.0-<date>-arm64_bvN.img
fastboot flash boot ~/a7lite/fw/new-boot.img
fastboot reboot recovery
adb shell twrp format data
adb reboot
```

`is-userspace` must say `yes`; otherwise you are not in TWRP fastbootd. Do not use `fastboot reboot` to
finish—reboot recovery, format data, then reboot normally. First boot is slow. During setup, skip Wi-Fi
until the launcher appears, then connect normally.

For a Google build, substitute the `arm64_bgN-signed` GSI in the commands above. Do not flash a separate
GApps ZIP into `/system`.

## Optional: Magisk

Patch the same SPL-matched `new-boot.img`, not the original stock boot. Install Magisk, patch the file in
the app, then flash the returned image from fastbootd:

```bash
adb reboot fastboot
fastboot flash boot magisk-boot.img
fastboot reboot
```

## Quick fixes

- `fastboot flash` says `unknown command`: that is Samsung's limited bootloader fastboot, not fastbootd.
  Boot TWRP first, then use **Reboot → Fastboot**.
- Stock recovery reappears: re-write TWRP and boot directly to recovery; do not boot Android in between.
- Black-screen GSI bootloop: confirm it is regular `arm64_bvN`/`bgN`, not vndklite, then format data in
  TWRP and flash again.
- A PIN causes a blank-screen loop: re-patch boot with the GSI's current security-patch month.

The post-install tweaks are in [the repository README](../README.md). This conversion is intentionally
limited to the SM-T227U; it is not a guide for the Wi-Fi SM-T220 or international SM-T225.
