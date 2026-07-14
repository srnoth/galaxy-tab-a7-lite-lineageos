# Playbook — Samsung SM-T227U (US carrier) → Canadian XAC firmware → LineageOS GSI

**What this does:** Takes a bootloader-**locked**, US-carrier Samsung Galaxy Tab A7 Lite
**SM-T227U** (codename `gta7lite`, MediaTek MT8768T / MT6765) and converts it, end to end, into a
device running a clean **LineageOS 21 (Android 14) GSI** — suitable for a Home Assistant wall-dashboard
kiosk or any de-Googled use. The US carrier firmware never exposes an OEM-unlock toggle; cross-flashing
the Canadian (XAC) firmware plus a MediaTek BootROM exploit is what unlocks it.

**This is validated on real hardware** (two separate SM-T227U units, 2026-07-12). Every command and every
gotcha below was executed and confirmed, including several that contradict the generic online guides.

**How to run it.** The procedure is written as **two roles**: a *driver* that types the commands (over
SSH into the Linux workbench) and an *operator* physically at the tablet doing the button/USB combos.
The driver can be **you**, or an agentic LLM assistant (this playbook was authored while a Claude Code
agent drove the commands over SSH and a human did the physical steps) — the phases and gotchas are the
same either way. You can also just do both roles yourself.

> **⚠️ Disclaimer.** Flashing firmware can permanently brick a device and voids warranties. This is a
> right-to-repair / device-owner guide provided **as-is, without warranty**. Only do this on hardware you
> own. **Phase 1 (a complete BootROM backup) is mandatory** — it is what makes mistakes recoverable. You
> proceed at your own risk.

> ⚠️ **Read this first — feasibility gate.** This procedure is specific to the **SM-T227U** and to the
> target firmware **`T227UVLSCFYE2` (XAC)**. It works because bootloader revision **"C"** is the
> model-wide ceiling for the entire SM-T227U line (US and Canada both topped out at BL "C" in May 2025).
> Flashing XAC "C" onto a US "C" (or lower) device is an *equal-or-higher* bootloader write, which
> Samsung anti-rollback permits. **Do NOT substitute an older XAC build** (bootloader 9/A/B) — if the
> device ever took the May-2025 update that would be a *downgrade* and can **hard-brick** the bootloader.
> If you are on a different model or a newer firmware exists by the time you read this, re-verify the
> bootloader-ceiling logic before proceeding.

---

## 0. Mental model & the three things that keep you safe

- **The BootROM (BROM) is your safety net.** The MT8768T's mask-ROM BootROM is exploitable with the
  open-source **mtkclient** (Kamakiri exploit, device USB ID `0e8d:0003`). As long as you have a
  **complete partition backup**, almost any software mistake is recoverable by re-writing partitions
  over BROM. **Do the backup (Phase 1) and do not skip it.** BROM reachability + a verified backup are
  the real safety gates — not anti-rollback.
- **Anti-rollback is a red herring here** (given the correct target FW above). An equal-bootloader
  cross-flash that somehow violated a fuse would simply make Odin *abort* — it is not the brick risk.
  The brick risk is flashing a *lower* bootloader, which the target-FW rule prevents.
- **This is a MediaTek Samsung, so two "normal" tools don't behave as documented** (learned the hard
  way; see the Gotchas box). Follow the phases exactly.

### 🔑 Gotchas that will waste hours if you don't know them

| # | Gotcha | Consequence / rule |
|---|--------|--------------------|
| G1 | **Each mtkclient/BROM op needs a FRESH BROM entry**, and USB must be **clear** (no `0e8d`/`04e8` device enumerated) *before* you arm mtkclient. | If a stale device is on the bus, mtkclient grabs it and exits `"Please disconnect… reconnect"` **without writing**. Always: verify USB clear → arm mtkclient → *then* operator does the BROM plug. |
| G2 | The tablet has a **battery**, so unplugging ≠ power off. | To fully power off from ANY state (fastboot, recovery, Android, hung): **hold Power + Vol-Up + Vol-Down ~10 s** until the screen is black. |
| G3 | **Samsung's LK bootloader-fastboot is reboot-only.** `fastboot flash …` returns `remote: 'unknown command'`; `fastboot reboot download` → `unknown reboot target`. | You cannot flash from bootloader-fastboot. Real flashing is Odin (Download mode) or mtkclient (BROM). |
| G4 | **Samsung stock recovery has NO fastbootd.** `adb reboot fastboot`, `fastboot reboot fastboot`, and BCB `boot-recovery`/`--fastboot` all silently **bounce to Android**. | The ONLY way to reach fastbootd (needed to flash the GSI into the dynamic `super` partition) is **through TWRP** → Reboot → Fastboot. |
| G5 | **On stock Samsung firmware, recovery entry is combo-only** — `adb reboot recovery` and a BCB `boot-recovery` in `misc` just bounce to Android (confirmed twice during conversion). **This is a stock-firmware trait, NOT permanent.** | During the **conversion** (Phases 1–5, still on Samsung/mid-flash) reach recovery by **hardware combo** (Power + Vol-Up). **Once LineageOS is running it's fixed:** `adb reboot recovery` and power-menu → Restart → Recovery both reach TWRP — so all post-conversion work (§3 updates, re-flashing) needs **no button combo and no operator**. |
| G6 | **A normal Android boot RESTORES stock recovery over TWRP.** | After writing TWRP, do **NOT** let it boot to Android. Go **straight to recovery via the combo** so TWRP survives. |
| G7 | The `recovery` partition is **32 MB** but TWRP's image is ~37 MB. | mtkclient writes only the first 32 MB and guards the size — this is **fine**: the real boot content (kernel+ramdisk+dtb ≈ 31.4 MB) fits; the truncated tail is just zero-pad + an AVB footer (irrelevant, verity disabled). |
| G8 | **Use the REGULAR `arm64_bvN` GSI, NOT `-vndklite`.** | The XAC A14 vendor is full-VNDK; a vndklite GSI mismatches linker namespaces and **bootloops** (black screen, no boot animation). Every GSI reported booting on this device is a regular build. |
| G9 | After flashing the GSI, **Format Data again and reboot to system from TWRP** — do NOT `fastboot reboot` straight to system. | Skipping the post-flash Format Data leaves dirty/encrypted userdata vs the FBE-patched fstab → bootloop. |
| G10 | **A vanilla GSI can't use a screen lock** unless boot & system agree on the SPL: set a PIN → reboot → rejected in a blank-screen loop. | Keymaster requires the **boot** image's `os_patch_level` to equal the **system** SPL. Stock XAC boot = `2025-05`; GSI system = `2026-xx` → mismatch. Fix = **SPL-match the boot in Phase 5** (flashed alongside the GSI, so the lockscreen works from first boot). Magisk-independent (seen on the stock boot too). |

---

## 1. Prerequisites

### Hardware
- The **SM-T227U** to convert (factory-reset recommended; no carrier financing lock).
- A **Linux workbench** with a native USB-A port (bare metal, **NOT a VM** — the BROM handshake window
  is <1 s and VM USB passthrough is unreliable). Ubuntu 22.04/24.04/26.04 all fine. A mature laptop
  (e.g. an older ProBook) is ideal.
- A good USB-A ↔ USB-C data cable.
- An **operator** physically at the tablet to do button+USB combos, and a **Claude Code** (or a person)
  driving the commands — ideally over SSH into the workbench so the two roles are cleanly separated.

### Firmware & images (download to the workbench, e.g. `~/a7lite/`)
1. **Full XAC firmware `T227UVLSCFYE2`** (5 files: BL / AP / CP / CSC / [USERDATA]) as `tar.md5` — via
   Frija, SamFW, or samfrew. Extract the AP `super`, `boot`, `recovery`, `vbmeta`, etc. as needed
   (`tar` → `lz4 -d`). The whole `tar.md5` set can be fed to odin4 directly. **Keep the extracted stock
   `boot.img`** — Phase 5's lockscreen SPL-match patches it.
2. **gta7lite TWRP v2.2** — `TWRP_v2.2_gta7lite.tar` (release notes: *"Fixed Fastbootd"*) and
   `fbe_disabler_gta7lite.zip`, from
   `https://github.com/gta7lite/teamwin_device_samsung_gta7lite/releases`.
3. **GSI: AndyYan LineageOS 21 pre-QPR2 TrebleDroid, regular `arm64_bvN` (vanilla, NOT vndklite)** —
   from `https://sourceforge.net/projects/andyyan-gsi/files/lineage-21-pre-qpr2-td/`
   → `lineage-21.0-<date>-UNOFFICIAL-arm64_bvN.img.gz`. `gunzip` it to a raw `.img`.
   (If Lineage ever misbehaves, the community's most-praised alt is crDroid `arm64_bgN`.)
   → **Want Google apps?** Grab `…-arm64_bgN-signed.img.gz` instead (regular, NOT vndklite) — see the
     "Optional — Google apps" section; do not plan to sideload a GApps zip afterward.
4. **`magiskboot`** — standalone boot-image tool used to SPL-match the boot (Phase 5 / §3). It ships inside
   the official Magisk APK (`github.com/topjohnwu/Magisk/releases`); extract the one binary (this is **not**
   installing root):
   ```bash
   cd ~/a7lite/fw && unzip -o -j Magisk-v*.apk lib/x86_64/libmagiskboot.so && mv -f libmagiskboot.so magiskboot && chmod +x magiskboot
   ```

### Toolchain on the workbench
```bash
# System deps
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libusb-1.0-0 lz4 \
                    android-tools-adb android-tools-fastboot simg2img
# Kill USB port-stealers (the #1 cause of BROM handshake failure)
sudo systemctl disable --now ModemManager 2>/dev/null; sudo systemctl mask ModemManager
sudo apt -y remove brltty 2>/dev/null || true
# mtkclient
git clone https://github.com/bkerler/mtkclient ~/a7lite/mtkclient
cd ~/a7lite/mtkclient && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
sudo cp mtkclient/Setup/Linux/*.rules /etc/udev/rules.d/ 2>/dev/null || \
     sudo cp Setup/Linux/*.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG plugdev,dialout "$USER"   # re-login for group changes
# odin4 (official Samsung Odin v4 Linux CLI) — place the `odin4` binary in ~/a7lite/odin/
# udev for Samsung Download mode + Google fastboot:
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="04e8", MODE="0666", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/51-android.rules
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"' | sudo tee -a /etc/udev/rules.d/51-android.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```
Sanity: `./.venv/bin/python ~/a7lite/mtkclient/mtk.py --help`, `odin4 -h`, `adb version`, `fastboot --version` all run.

### The BROM entry ritual (you will do this several times — memorize it)
1. Operator: **fully power off** the tablet (G2) and **unplug USB**.
2. Driver: verify the bus is clear — `lsusb | grep -iE '0e8d|04e8|18d1'` prints nothing (G1).
3. Driver: **arm** the mtkclient command (it prints "waiting for device").
4. Operator: **press & hold Vol-Up, then plug in USB**, keep holding until it connects.
5. Driver: watch for `lsusb` to show `0e8d:0003` and mtkclient to report the Kamakiri/DA handshake.

---

## 2. Phase-by-phase procedure

### Phase 1 — Full backup (BROM) — **mandatory brick insurance**
BROM entry (ritual above), then read back every partition + the preloader:
```bash
cd ~/a7lite/mtkclient
./.venv/bin/python mtk.py rl ~/a7lite/backup/rl_all --skip userdata   # all partitions (skip huge userdata)
# separately grab the preloader (boot1):
./.venv/bin/python mtk.py r preloader ~/a7lite/backup/preloader_boot1.bin --parttype boot1
```
Store the backup **off-device**. Confirm `misc.bin`, `recovery.bin`, `vbmeta.bin`, `boot.bin`, etc. exist.
**Gate B: do not proceed without a complete backup.**

### Phase 2 — Cross-flash to XAC firmware (Odin / Download mode)
1. Operator: **Download mode** — power off → hold **Vol-Up + Vol-Down** while plugging in USB → press
   **Vol-Up once** to confirm the blue Download screen.
2. Driver: flash the full XAC set (device VID in Download mode = `04e8:685d`):
   ```bash
   odin4 -b BL_T227UVLSCFYE2_*.tar.md5 \
         -a AP_T227UVLSCFYE2_*.tar.md5 \
         -c CP_T227UVLSCFYE2_*.tar.md5 \
         -s CSC_OYV_T227U*_*.tar.md5 --reboot
   ```
   (Use the CSC — not HOME_CSC — for a clean wipe. This is a kiosk.) Expect `RES OK` / PASS.
3. Let it boot once. **Gate C:** confirm it's XAC — the default setup-wizard language offers
   **"English (Canada)"**, and Download mode shows the XAC version.

### Phase 3 — Unlock bootloader + disable verity (BROM) — **order is critical**
BROM entry, then:
```bash
cd ~/a7lite/mtkclient
# 1) UNLOCK first:
./.venv/bin/python mtk.py da seccfg unlock
```
(Works on XAC FW; no-ops/fails on US FW. The OEM-unlock toggle never appears — this exploits below it.
Next boot forces a factory reset — expected.) **Then, a fresh BROM entry**, and:
```bash
# 2) DISABLE verity/verification — AFTER unlock, BEFORE first Android boot:
./.venv/bin/python mtk.py da vbmeta 3        # 3 = disable verity + verification
```
> ⚠️ Ordering rules: vbmeta patching invalidates the AVB signature. On a still-**locked** bootloader
> that = red state / won't boot, so it MUST come **after** `seccfg unlock`. And it must be **after** the
> Odin flash (Odin rewrites vbmeta to stock). Doing it here removes the text **"dm-verity corruption…
> shuts down in 5 s"** screen permanently, leaving only the orange "bootloader unlocked" warning, which
> **auto-continues on its own** (fine for an unattended kiosk).

**Gate D:** device is unlocked (`flash.locked=0`, `verifiedbootstate=orange`) and verity is off.

### Phase 4 — Flash TWRP (BROM) and boot into it (combo, NOT normal boot)
Samsung LK-fastboot can't flash (G3) and stock recovery has no fastbootd (G4), so write TWRP over BROM.
1. Extract the recovery image from the tar:
   ```bash
   cd ~/a7lite/twrp && tar xvf TWRP_v2.2_gta7lite.tar   # yields recovery.img (~37 MB)
   ```
2. BROM entry, then write it (size-truncation to 32 MB is expected and harmless — G7):
   ```bash
   cd ~/a7lite/mtkclient
   ./.venv/bin/python mtk.py w recovery ~/a7lite/twrp/recovery.img
   ```
   (Do **not** bother writing a BCB — this bootloader ignores it, G5.)
3. **Boot straight into TWRP via the combo (G6) — do NOT do a normal power-on:**
   - Operator: force off (G2), then **hold Power + Vol-Up**. At the orange warning, **release, tap
     Power once, then immediately re-hold Power + Vol-Up** (two-stage; you can't hold continuously).
   - You should land in **TWRP 3.7.1** (teal). Confirm over USB: `adb devices` shows
     `recovery … product:twrp_gta7lite`.
   > If you instead reach stock recovery, a normal boot restored it (G6) — re-write TWRP (step 2) and
   > combo again *without* letting Android run in between.

### Phase 5 — Flash the GSI + SPL-matched boot (fastbootd via TWRP)
Driven over `adb`/`fastboot` from the workbench. **First, on the host, SPL-match the stock boot** so the
lockscreen works from the first boot (G10) — read the GSI's SPL straight off the image and patch `boot.img`:
```bash
cd ~/a7lite/fw
grep -a -o 'ro.build.version.security_patch=[0-9-]*' lineage-21.0-<date>-*-arm64_bvN.img   # -> e.g. ...=2026-06
./magiskboot unpack -h boot.img
sed -i 's/^os_patch_level=.*/os_patch_level=2026-06/' header      # ← the YEAR-MONTH from above
./magiskboot repack boot.img                                     # -> new-boot.img
```
Then flash the GSI **and** the matched boot together:
```bash
# In TWRP: disable File-Based Encryption, then format data
adb push ~/a7lite/twrp/fbe_disabler_gta7lite.zip /tmp/fbe.zip
adb shell twrp install /tmp/fbe.zip          # -> "Finished Disabling FBE"
adb shell twrp format data                   # -> Done

adb reboot fastboot                          # REAL fastbootd — stock recovery could never give us this
fastboot getvar is-userspace                 # must print: is-userspace: yes

fastboot erase system
fastboot delete-logical-partition product    # headroom; GSI (~2.55 GB) fits the ~3.49 GB slot anyway
fastboot flash system ~/a7lite/fw/lineage-21.0-<date>-arm64_bvN.img   # ⚠ REGULAR bvN, not vndklite (G8)
fastboot flash boot   ~/a7lite/fw/new-boot.img                       # SPL-matched boot (fastbootd refuses? BROM: mtk.py w boot new-boot.img)

# CRITICAL finish (G9): recovery, format data AGAIN, then boot
fastboot reboot recovery
adb shell twrp format data
adb reboot                                   # normal boot -> GSI
```
**First boot takes several minutes** (ART cache); success = a real **LineageOS boot animation**, not a black
screen. Because boot & system now share an SPL, you can set a lockscreen PIN normally.

### Phase 6 — First boot & LineageOS setup
- In the setup wizard: **no SIM, and SKIP Wi-Fi** during setup (known first-boot bootloop-avoidance on
  this device). Connect Wi-Fi after setup completes.
- In LineageOS Updater / setup, **do NOT enable "update Lineage recovery alongside the OS"** — it would
  overwrite TWRP (your only fastbootd path) and GSI OTAs don't work on this device anyway.
- Enable Developer Options → USB debugging if you want continued `adb` access.

### Optional — Google apps (GApps) or microG
The build in Phase 5 is **vanilla (no Google)**. If you want Google services, the important thing to know
for this dynamic-partition/GSI setup is:

> ⚠️ **Do NOT flash a separate GApps zip (NikGapps/MindTheGapps) into `/system` via TWRP.** The GSI's
> `system` is **read-only and sized tight to the image**; making it writable and resizing the logical
> partition to fit GApps is fragile and usually fails here. **Instead, pick a GApps-included GSI at flash
> time** — GApps baked in, no post-flash gymnastics.

- In Phase 5, flash the **`arm64_bgN`** variant instead of `arm64_bvN` (`g` = gapps, `v` = vanilla):
  `lineage-21.0-<date>-UNOFFICIAL-arm64_bgN-signed.img`. **Everything else in Phases 4–5 is identical.**
- **Same two constraints apply:** it must be the **REGULAR build, NOT `-vndklite`** (there is a
  `bgN-vndklite` — don't use it; same full-VNDK reason as G8), and it must fit the **~3.49 GB `system`
  slot**. `bgN` is ~3.2 GB decompressed (vs ~2.55 GB for `bvN`) → it fits, but keep the
  `fastboot delete-logical-partition product` step for headroom (fastbootd auto-grows `system`).
- **microG alternative (lighter, de-Googled):** if you only want push notifications (e.g. an HA Companion
  app's FCM) without full Google, flash the **vanilla `bvN`** and install **microG** (needs signature
  spoofing) as user apps — no GApps in `/system`. Better for an unattended kiosk.

### End of conversion
At this point the tablet is a clean, bootloader-unlocked, de-Googled **LineageOS 21** device. **This is
where the model-conversion playbook ends.**

Whatever you do with it next — kiosk app, HA dashboard, WebView/performance tuning, MDM, etc. — is
**out of scope for this playbook** and is use-case–specific, not SM-T227U–specific. (For the Home
Assistant wall-kiosk use case this device was converted for, the Fully-Kiosk / System-WebView / Lovelace
tuning is tracked separately on the HA side of the project.)

Sections **2b** and **2c** below are **optional** and device-specific: root, and the small systemless tweaks
that fix things the GSI gets wrong on this tablet. Stop at this line and you still have a perfectly good
stock LineageOS tablet.

---

## 2b. Optional — Root with Magisk

Not required for anything above. You want it if you intend to apply any of the
[Magisk tweaks](#2c-optional--magisk-tweaks) below, or want genuine hardware screen control for a kiosk.

> ⚠️ **Patch the SPL-MATCHED boot from Phase 5 — not the raw stock boot.** Magisk preserves the boot header,
> so the `os_patch_level` you set in Phase 5 carries through and the lockscreen keeps working (G10). Patch
> the stock boot instead and you'll walk straight back into the PIN loop.

```bash
# 1) Install the Magisk app and give it the Phase-5 SPL-matched boot to patch:
adb install Magisk-v*.apk
adb push new-boot.img /sdcard/Download/        # the SPL-matched boot you flashed in Phase 5
#    In the Magisk app: Install → "Select and Patch a File" → pick new-boot.img
adb pull /sdcard/Download/magisk_patched-*.img ./magisk-boot.img

# 2) Flash it. No button combo needed — fastbootd is reachable from a booted LOS:
adb reboot fastboot
fastboot flash boot magisk-boot.img
fastboot reboot
```
Verify: the Magisk app reports installed, and `adb shell su -c id` returns `uid=0`.

**This survives a LineageOS update** if you follow §3 — that flow pulls the *current* boot off the device and
only bumps its SPL, so whatever is on it (including Magisk) is carried over.

---

## 2c. Optional — Magisk tweaks

Small, systemless, individually toggleable. Nothing here modifies `/system`.

> **Why everything here is a Magisk module and never "just copy a file into `/system`":** the GSI `system`
> image is built ext4 with the **`shared_blocks`** feature (block dedup), and the kernel **forces such a
> filesystem read-only** — **TWRP cannot write to it.** Un-sharing it (`e2fsck -E unshare_blocks`) does work
> but costs ~700 MB and needs the image grown first; *and* Android reads `/system` SELinux labels from the
> image's `security.selinux` xattrs, which you can't set from an ordinary Linux host (no SELinux LSM —
> `chcon` silently no-ops). This is the same reason the GApps warning above tells you not to flash GApps
> into `/system`. Magisk modules live in `/data/adb/modules`: systemless, reversible with a toggle, and they
> **survive the §3 GSI update**.

### Adaptive brightness — **[`magisk/gta7lite-autobrightness/`](../magisk/gta7lite-autobrightness/)**

**Symptom:** no **"Adaptive brightness"** toggle in Settings → Display, and the screen never responds to
ambient light — even though this tablet *has* a working light sensor (AMS `tsl2540`, listed in
`adb shell dumpsys sensorservice`).

**Cause — one boolean.** From LineageOS 21 `DisplayDeviceConfig.java`:
```java
mAutoBrightnessAvailable = res.getBoolean(R.bool.config_automatic_brightness_available)
                           && mDdcAutoBrightnessAvailable;
```
`config_automatic_brightness_available` is a **framework resource**. AOSP's default is `false`; real devices
override it in their own device overlay — and **a GSI has no device overlay**, so it stays `false` and the
auto-brightness controller is never constructed. No setting or `displayconfig` XML can turn it on (that XML
path can only turn it *off*), so it takes a **runtime resource overlay**. The module is that overlay, and it
contains exactly one line.

> 🔑 **The lux→backlight curve is NOT missing.** A GSI only replaces `/system`; your **stock Samsung
> `/vendor` is untouched**, and `/vendor/overlay/FrameworkResOverlay` still holds the factory-tuned curve for
> this exact panel. Flip the boolean and Samsung's own curve runs. **Do not write your own** — and be wary of
> GSI "brightness fix" modules that ship one, because it will be some other phone's panel.

```bash
adb push gta7lite-autobrightness-v2.zip /data/local/tmp/
adb shell su -c "magisk --install-module /data/local/tmp/gta7lite-autobrightness-v2.zip"
adb reboot
```

**Verify** (a static RRO does **not** appear in `cmd overlay list` — check the flag, not the list):
```bash
adb shell dumpsys display | grep -o 'mAutoBrightnessAvailable= [a-z]*'   # must say: true
adb shell settings put system screen_brightness_mode 1                    # turn adaptive brightness on
adb shell dumpsys display | grep -m1 mAmbientLux                          # live lux — cover the sensor, watch it fall
```
Measured on hardware: 0 lux → backlight 5/255 · 242 lux → 80/255 · 15,848 lux (flashlight) → 255/255.

**Don't stack the phh brightness options on top of it** — see
[post-install tweaks §3](post-install-tweaks.md#-brightness-options--leave-them-off).

---

## 3. Updating to a newer LineageOS build (later)
No OTAs on GSIs (that's why "update Lineage recovery" stays **off** — it would eat TWRP). An update =
flash the new `system` + a re-SPL-matched `boot`, together in one fastbootd session. Just **pull the
current boot from the device and bump its SPL**: this carries over whatever's on it (including Magisk, if
you added it) and only realigns the patch level — the kernel is stock XAC and doesn't change across LOS
builds.

```bash
# 1) From booted LOS, reboot to TWRP over adb (works on LOS — G5; no combo/operator needed), then pull the
#    current boot and read the NEW build's SPL off its image:
adb reboot recovery                                          # or power menu -> Restart -> Recovery; wait for TWRP
adb shell dd if=/dev/block/by-name/boot of=/sdcard/boot-live.img && adb pull /sdcard/boot-live.img ~/a7lite/fw/
cd ~/a7lite/fw
grep -a -o 'ro.build.version.security_patch=[0-9-]*' lineage-21.0-<newdate>-*-arm64_bvN.img   # -> e.g. ...=2026-09

# 2) Bump the pulled boot's SPL to that value:
./magiskboot unpack -h boot-live.img
sed -i 's/^os_patch_level=.*/os_patch_level=2026-09/' header      # ← new YEAR-MONTH
./magiskboot repack boot-live.img                                # -> new-boot.img

# 3) In fastbootd, flash both and reboot:
adb reboot fastboot ; fastboot getvar is-userspace               # is-userspace: yes
fastboot erase system
fastboot flash system ~/a7lite/fw/lineage-21.0-<newdate>-*-arm64_bvN.img
fastboot flash boot   ~/a7lite/fw/new-boot.img                   # (fastbootd refuses? BROM: mtk.py w boot new-boot.img)
fastboot reboot recovery ; adb shell twrp wipe cache ; adb shell twrp wipe dalvik ; adb reboot
```
Because boot & system share the SPL, your existing PIN keeps working — no locked-out state. First boot is
slow (ART rebuild). A same-variant update keeps data (wipe cache/dalvik as above); for a **variant/tree/
major-version** change use `adb shell twrp format data` instead (and expect to reconfigure).

---

## 4. Troubleshooting (all observed on real hardware)

- **mtkclient exits `"Please disconnect… reconnect"` without writing** → stale device on the bus (G1).
  Clear USB, re-arm, fresh BROM entry.
- **`fastboot flash …` → `remote: 'unknown command'`** → you're in Samsung LK bootloader-fastboot, not
  fastbootd (G3). You cannot flash here; use Odin or mtkclient, or reach fastbootd via TWRP.
- **`adb reboot fastboot` boots to Android instead of fastbootd** → you're on stock recovery (G4); it
  has no fastbootd. Install TWRP first.
- **Combo boots to stock recovery / setup wizard instead of TWRP** → a normal boot restored stock
  recovery (G6), or the two-stage combo mistimed. Re-write TWRP over BROM and combo straight in.
- **GSI bootloops: black screen after the orange warning, no boot animation, reboots** → the classic
  two causes: **(a)** you flashed `-vndklite` instead of regular `arm64_bvN` (G8); **(b)** you skipped
  the post-flash Format Data / did `fastboot reboot` straight to system (G9). Fix both: re-flash the
  regular build and finish with `fastboot reboot recovery` → `twrp format data` → `adb reboot`.
- **Set a PIN, reboot, it's rejected (blank screen, loops)** → boot/system **SPL mismatch** (G10), not a
  typo. Re-SPL-match `boot` to `ro.build.version.security_patch` (Phase 5 / §3). If already locked out,
  **Format Data** in TWRP first, then flash the SPL-matched boot. (Magisk-independent.)
- **Read the actual crash cause** from TWRP after a bootloop: `adb pull /sys/fs/pstore/`
  (`console-ramoops-0`), or `adb shell cat /proc/last_kmsg`; grep for `fs_mgr`/`mount`/`avb`/linker
  namespace errors. (Note: a clean init-reboot may leave pstore empty — absence of a panic itself
  points at a mount/decrypt failure rather than a kernel crash.)

## 5. Gate checklist (stop if any fails)
- **A — Feasibility:** device current bootloader char ≤ target XAC char (C). Any real US build satisfies this.
- **B — Backup:** complete mtkclient partition backup exists off-device before ANY write.
- **C — Cross-flash:** Download mode shows XAC `T227UVLSCFYE2`; boots; setup offers English (Canada).
- **D — Unlock:** `flash.locked=0`, `verifiedbootstate=orange`; verity disabled (vbmeta patched).
- **E — TWRP:** `adb devices` shows `product:twrp_gta7lite`; TWRP → Reboot → Fastboot yields `is-userspace: yes`.
- **F — GSI:** device boots to the LineageOS animation and reaches setup; touch + Wi-Fi work.
- **G — Lockscreen (optional):** a PIN set in Settings survives a reboot. If it loops, boot `os_patch_level`
  ≠ system SPL — redo the SPL-match (Phase 5 / §3).

---

### Provenance
Validated 2026-07-12 on a Metro/T-Mobile SM-T227U. The device-specific write methods (mtkclient for
TWRP, combo-to-recovery, regular-not-vndklite, format-data-last) diverge from the generic XDA guides on
purpose — the generic guides assume Odin ride-in and don't cover this bootloader's BCB/fastbootd
quirks. Primary external sources: the SM-T227U-tested XDA "Flash a GSI on the A7 Lite (with TWRP)"
guide, the gta7lite TWRP repo, AndyYan's GSI builds, and the SM-T227U cross-flash unlock thread.

The lockscreen boot-SPL match (Phase 5 / §3) was diagnosed and validated 2026-07-13 on **both** SM-T227U
units: matching the boot image's `os_patch_level` to the GSI's system SPL restores PIN/password unlock
across reboots. Also hardware-confirmed on this device that day: `fastboot flash boot` works in fastbootd,
and `adb reboot recovery` reaches TWRP once LineageOS is running (G5) — so Phase 5's boot flash and all §3
updates need no button combo or operator.

> ⚠️ **Security note — `/data` is NOT encrypted.** `fbe_disabler` (Phase 5) removes File-Based Encryption
> so the GSI will boot, which leaves userdata in **plaintext**: a lockscreen PIN gates the running UI but
> does **not** protect data at rest — anyone who boots TWRP or images the flash can read everything. As of
> 2026-07 the GSI/Treble communities have **no** working data-at-rest encryption on Samsung MediaTek GSIs
> (the vendor TEE Keymaster can't drive FBE under a GSI — the same subsystem behind the SPL lockscreen
> bug); disabling it is the universal workaround. Fine for a kiosk; for a daily-driver holding real
> accounts, treat these as unencrypted and use an app-level vault (e.g. Cryptomator) for anything sensitive.
