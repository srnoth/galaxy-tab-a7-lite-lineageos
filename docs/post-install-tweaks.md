# Post-install fixes & tweaks — `gta7lite` on LineageOS

Things worth doing *after* [the conversion](conversion-playbook.md) boots. Everything here was validated on
real SM-T227U hardware; anything unverified says so explicitly.

---

## 1. Screen turns itself on in an endless loop (lockscreen set to "None")

**Symptom.** The screen times out and goes dark, then **turns itself back on a few seconds later**, sits for
the full screen timeout, goes dark, turns back on… forever. It never stays asleep. Measured rate: **~170
screen-ons per hour**.

**When it happens.** Only when the **screen lock is set to "None"** *and* the screen goes off by
**inactivity timeout**. Pressing the power button to sleep it does **not** trigger the loop — which is a
great red herring, because it makes the bug look intermittent.

### The fix (one command, no root)

```bash
adb shell settings put secure lock_screen_lock_after_timeout 0
```

The lockscreen **stays disabled** — which is the whole point if you're building a kiosk.

### Why

This is stock **LineageOS/AOSP** code, not a GSI or phh quirk. Any LineageOS device with the lock type set
to "None" should reproduce it.

In `SystemUI`'s `KeyguardViewMediator.java`:

```java
private void handleHide() {
    // It's possible that the device was unlocked (via BOUNCER) while dozing. It's time to wake up.
    if (mAodShowing) {
        mPM.wakeUp(..., PowerManager.WAKE_REASON_GESTURE, "com.android.systemui:BOUNCER_DOZING");
    }
```

`mAodShowing` is **not** "the AOD panel is on" — it's assigned `mDozing && !mWakeAndUnlocking`. It just means
*dozing*. So the display gets woken whenever the keyguard is **hidden while the device is dozing**. The chain:

1. Screen off **by timeout** → `doKeyguardLaterLocked(timeout)` schedules a delayed-lock alarm.
   `timeout` = `Settings.Secure.LOCK_SCREEN_LOCK_AFTER_TIMEOUT`, default `KEYGUARD_LOCK_AFTER_DELAY_DEFAULT = 5000`.
2. Device enters doze → `mAodShowing = true`.
3. 5 s later the alarm fires → `doKeyguardLocked()` → sees lock type is None → calls `hideLocked()`.
4. `handleHide()` sees `mAodShowing` → **wakes the screen.**
5. Screen timeout → back to step 1.

Setting the timeout to `0` fails the `timeout > 0` test in step 1, so the alarm is never scheduled and the
chain never starts. (Power-button-off takes a different branch that schedules nothing — that's why it "fixes"
it too.)

Three things independently suppress this bug — useful to know so they don't confound your testing:
a keyguard that is *showing*, a power-button screen-off, and `lock_after_timeout = 0`.

### ⚠️ Kiosk warning — Fully Kiosk will re-trigger this

Fully Kiosk's "disable lockscreen" (as Device Owner) calls `DevicePolicyManager.setKeyguardDisabled(true)`,
which internally does `mLockPatternUtils.setLockScreenDisabled(disabled, userId)` — **the exact same flag**.
It also *refuses* to run if a PIN is set, so keeping a PIN is not an available workaround.

`lock_screen_lock_after_timeout = 0` still fixes it (it disarms the alarm rather than relying on a keyguard
existing) — but **it's a Secure setting, so a factory reset wipes it**, and Device Owner provisioning
*requires* a freshly reset device. Correct order:

> factory reset → `dpm set-device-owner` → **re-apply the command above** → verify

*Unverified:* the same code also consults DevicePolicy `getMaximumTimeToLock()`. If a Device Owner sets a
max-time-to-lock > 0 it might override the `0` and rearm the loop. Re-test after provisioning.

### Verify

Let the screen idle-timeout (do **not** press power — that hides the bug), then a minute later:

```bash
adb shell dumpsys power | grep mWakefulness=      # should still say: Dozing
```
Regression signature in logcat:
`Waking up from Dozing (... details=com.android.systemui:BOUNCER_DOZING)`

---

## 2. Airplane mode that kills only the modem (keeps Wi-Fi up)

The LTE models (SM-T225/T227) keep the modem awake scanning **even with no SIM installed** — visible as
`PHH-Radio: signalLevelInfoChanged` roughly **once every 1.3 s** in logcat. Pure wasted CPU on a Wi-Fi-only
wall kiosk.

Airplane mode fixes that, but by default it also kills Wi-Fi. Change *which radios* it touches:

```bash
adb shell settings put global airplane_mode_radios cell
# default was: cell,bluetooth,uwb,wifi,wimax
```

Now enable Airplane Mode. **Validated:** `airplane_mode_on=1`, Wi-Fi stayed associated (−34 dBm, still on the
LAN), and `PHH-Radio` chatter went from ~1 line/1.3 s to **0 lines in a 20-second sample**.

> **Do NOT use phh Treble Settings → "Remove Telephony Subsystem" for this.** That runs
> `rm -Rf /system/priv-app/TeleService` against a remounted `/system` and reboots. It is **irreversible**
> without reflashing the GSI. Airplane mode achieves the same silence and is a toggle.

---

## 3. phh / TrebleDroid "Treble Settings" — what to touch, on *this* device

The GSI ships a **Treble Settings** app (`me.phh.treble.app`) with ~90 toggles. Most are for other vendors'
hardware. Here's what's real on `gta7lite`.

### ☠️ Never

| Option | Why |
|---|---|
| **Securize** | Its dialog string is literally `remove_root` — it runs `phh-securize.sh` to strip root. (On the build I tested that script doesn't even exist, so it fails harmlessly — but don't.) |
| **Remove Telephony Subsystem** | `rm -Rf /system/priv-app/TeleService`. Irreversible without a GSI reflash. Use airplane mode (§2). |
| **Allow takeover of the device by phh for debugging** | Remote control of your tablet by the ROM author. |
| **Disable HW overlays** | phh's own summary says *"Eats more CPU and battery."* Wrong direction on a slow SoC. |
| **Force allow Always-On Display** | LCD panel; also pokes the same doze/keyguard machinery as the §1 bug. |

### ✅ Worth trying (the only options that touch rendering perf)

These are the MediaTek-specific ones, and we *are* MT6765. phh labels them "might improve" — that's
honest, they're speculative. **A/B them one at a time**, don't flip all four and declare victory.

- **Mediatek GED KPI support** (`persist.sys.phh.mtk_ged_kpi`)
- **Disable SF GL backpressure** (needs reboot)
- **Disable SF HWC backpressure**
- **Disable FUSE storage layer** (needs reboot — this eMMC is slow)

### ✅ Useful for a wall kiosk

- **Force navigation bar disabled** (reboot). Largely redundant once a kiosk app runs as Device Owner with
  lock-task, which hides it anyway.
- **Samsung → Enable double tap to wake.** **Confirmed supported** on this panel — `aot_enable` is present
  in the touchscreen's `cmd_list`. Note this *adds a wake source*; if you ever chase mystery wakes, turn it
  off first.
  > The **Misc** section's separate "Double tap to wake" is **not** the one you want — it only drives
  > Asus/Xiaomi/Agold paths, which is why its own summary admits *"Unlikely to work for you."*

### 🚫 Does nothing on this hardware

- **Doze → Handwave / out-of-pocket gestures** — there is **no proximity sensor** (`mProximitySensor=null`).
  They cannot work.
- Anything **fingerprint**-related (broken fingerprint, FOD single click, under-display fp colour, treat
  virtual sensors as real) — **no fingerprint sensor.**
- **Reversed wireless charging** — no wireless charging.
- All **camera** options, and the **IMS/VoLTE**, **5G display**, **SMSC**, **RIL restart** options if you
  run without a SIM.
- The **Qualcomm / Xiaomi / OnePlus / Oppo / Asus / Huawei** sections are vendor-gated and shouldn't appear.

### 🎨 Harmless

The **Custom** section (accent colour, icon shape/pack, font, pointer type) is purely cosmetic — zero
performance cost.

### ⚠️ Brightness options — leave them off

*Force alternative backlight scale*, *Set alternative brightness curve*, *Set linear brightness curve*,
*Allows setting brightness to the lowest possible*, *Samsung → backlight scale*. These rescale how a
brightness **value** maps to panel output — a **different layer** from the adaptive lux→value curve — and
exist for devices whose backlight scaling is broken under a GSI. **This device's isn't**: the stock vendor
overlay already provides `config_screenBrightnessSettingMinimum=3` / `Default=37` / `Doze=5`. Enabling these
will distort the correct factory curve. See [the adaptive brightness
module](../magisk/gta7lite-autobrightness/).

---

## 4. Hardware notes (what's actually in this tablet)

From `dumpsys sensorservice` / `dumpsys display` on a converted SM-T227U:

| Sensor | Present? | Notes |
|---|---|---|
| Accelerometer | ✅ `mc3419` (Memsic) | |
| Magnetometer | ✅ `af6133e` (VTC) | |
| **Ambient light** | ✅ **`tsl2540` (AMS)** | Works — but the GSI disables adaptive brightness. [Fix](../magisk/gta7lite-autobrightness/). |
| Grip sensor | ✅ `SX9325` (Semtech) | Samsung SAR sensor. Wake-capable. |
| Significant motion | ✅ (MTK) | Wake-capable. |
| **Proximity** | ❌ **None** | Kills the phh Doze handwave/pocket gestures. |
| **Fingerprint** | ❌ **None** | Kills every FOD/fingerprint option. |

Other facts worth knowing:
- **GPU is PowerVR GE8320, not Mali.** MediaTek performance mods often assume Mali — check before flashing.
- **3 GB RAM, eMMC, 8× Cortex-A53.** This is the performance floor; debloating barely moves it. The
  bottleneck is hardware, not bloat.
- **A GSI is system-only.** `boot` (the kernel) and `vendor` remain **stock Samsung** — so any ROM-to-ROM
  responsiveness difference is *userspace*, and kernel/thermal tuning applies regardless of ROM.

---

## 5. The lesson that generalizes

**A GSI only replaces `/system`. Your stock Samsung `/vendor` is still there — and so are its resources.**

Before hand-authoring any device resource for a GSI, look at what the factory already gave you:

```bash
adb root
adb pull /vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk
apktool d FrameworkResOverlay.apk
```

That's how the adaptive-brightness fix went from "invent a lux→backlight curve and hope" to "flip one
boolean and let Samsung's tuned curve run." I got it wrong the first time. **Check `/vendor` first.**
