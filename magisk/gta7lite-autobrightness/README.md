# Adaptive Brightness for Galaxy Tab A7 Lite on a LineageOS GSI

A ~8 KB Magisk module that enables **adaptive (automatic) brightness** on `gta7lite` running a LineageOS 21
GSI, where it is otherwise missing entirely — no toggle in Settings, no response to ambient light.

**[⬇ gta7lite-autobrightness-v2.zip](gta7lite-autobrightness-v2.zip)** — flash in Magisk, reboot.

---

## The problem

The tablet has a real, working ambient light sensor (**AMS `tsl2540`**). `dumpsys sensorservice` lists it.
But on a GSI, Settings has no *Adaptive brightness* toggle and the sensor is never even registered.

It isn't the hardware, and it isn't the sensor HAL. It's **one boolean**.

## The cause

From LineageOS 21 `services/core/java/com/android/server/display/DisplayDeviceConfig.java`:

```java
mAutoBrightnessAvailable = mContext.getResources().getBoolean(
        R.bool.config_automatic_brightness_available)
        && mDdcAutoBrightnessAvailable;
```

`mDdcAutoBrightnessAvailable` is already `true` on this device. But `config_automatic_brightness_available`
is a **framework resource**, and AOSP's default is `false` — real devices override it in their own device
overlay. **A GSI has no device overlay, so it stays `false`**, and `DisplayPowerController` never constructs
the auto-brightness controller at all.

You cannot fix this with a settings command or a `/product/etc/displayconfig` XML — that XML path can only
turn the flag *off*, never on. It requires a **runtime resource overlay (RRO)**.

## What the module does

Exactly one thing:

```xml
<bool name="config_automatic_brightness_available">true</bool>
```

Packaged as a **static RRO** targeting `android`, gated on `ro.vendor.build.fingerprint` matching
`*amsung/gta7litecs*` so it cannot load on the wrong device, and shipped systemlessly via Magisk into
`/system/product/overlay/`. `/system` is never modified.

## What the module deliberately does *not* do

**It does not ship a brightness curve.** This is the important part.

A GSI replaces `/system` only — your **stock Samsung `/vendor` partition is untouched**, and it still
contains `/vendor/overlay/FrameworkResOverlay`, which already carries the factory-tuned curve for this exact
panel:

```
config_autoBrightnessLevels            :  20, 50, 100, 200, 400, 1000, 2000, 3000, 5000
config_autoBrightnessLcdBacklightValues:  5, 26, 47, 57, 61, 95, 146, 186, 235, 255
config_screenBrightnessSettingMinimum  :  3
config_screenBrightnessDoze            :  5
```

Note the deliberate **plateau across normal indoor light** (100 lux → 57, 200 lux → 61): Samsung holds
brightness steady through the most common range instead of ramping through it. That is panel-specific tuning
you do not want to reinvent — and it was already on the tablet.

Most GSI "brightness fix" modules floating around ship *someone else's phone's* curve. This one flips the
flag and gets out of the way.

## Verify it worked

```bash
adb shell dumpsys display | grep -o 'mAutoBrightnessAvailable= [a-z]*'   # → true
adb shell settings put system screen_brightness_mode 1                    # enable adaptive
adb shell dumpsys display | grep -m1 mAmbientLux                          # live lux
```

Static RROs do **not** appear in `cmd overlay list` — check `mAutoBrightnessAvailable`, not the overlay list.

Measured on hardware (SM-T227U, LineageOS 21 GSI):

| condition | ambient lux | backlight |
|---|---|---|
| dark room | 0 | 5 / 255 |
| lit closet | 242 | 80 / 255 |
| flashlight on the sensor | 15,848 | 255 / 255 |

And the resulting spline, straight out of `dumpsys display` — Samsung's curve, point for point:

```
mSpline = MonotoneCubicSpline{[(0.0, 0.015748031), (20.0, 0.098425195), (50.0, 0.18110237),
  (100.0, 0.22047244), (200.0, 0.23622048), (400.0, 0.37007874), (1000.0, 0.57086617),
  (2000.0, 0.72834647), (3000.0, 0.9212598), (5000.0, 1.0)]}
```

## Tuning it to taste

Don't edit the curve. Just move the brightness slider while adaptive brightness is on — Android stores a
single gamma adjustment (`Settings.System.screen_auto_brightness_adj`) and bends the whole curve. To reset
to factory neutral:

```bash
adb shell settings put system screen_auto_brightness_adj 0.0
```

## Do NOT also enable the phh brightness options

phh/TrebleDroid Treble Settings has *Force alternative backlight scale*, *Set alternative brightness curve*,
*Set linear brightness curve*, and *Allows setting brightness to the lowest possible*. Those operate on a
**different layer** — how a brightness *value* maps to actual panel output — and exist for devices whose
backlight scaling is broken under a GSI. This one's isn't. Turning them on will distort the now-correct
factory curve. Leave them off.

## Rollback

Disable or remove the module in Magisk and reboot. Nothing in `/system` was ever changed.

## Compatibility

Built and validated **only** on **SM-T227U** (`gta7litecs`, XAC firmware, LineageOS 21 GSI).

The fingerprint gate means it will simply not load on anything else. If you have an **SM-T220
(`gta7litewifi`)** or **SM-T225**, the same defect almost certainly applies and the same one-line fix should
work — change `requiredSystemPropertyValue` in `src/AndroidManifest.xml` to match your
`ro.vendor.build.fingerprint` and rebuild. Please open an issue and tell me if it works; I only own T227U
units and won't claim what I can't test.

## Building from source

`src/` is the overlay, laid out to match [`phhusson/vendor_hardware_overlay`](https://github.com/phhusson/vendor_hardware_overlay)
so it can be upstreamed as-is.

```bash
sudo apt install apktool apksigner zipalign default-jdk-headless
apktool b -o unsigned.apk src
zipalign -f -p 4 unsigned.apk aligned.apk
apksigner sign --ks your.jks --out treble-overlay-samsung-gta7lite.apk aligned.apk
# then: system/product/overlay/treble-overlay-samsung-gta7lite.apk + module.prop → zip → flash
```

The released APK is signed `CN=srnoth`. The signing key is not in this repo. A static RRO on a system
partition is trusted by its partition, not its signature, so you can freely rebuild and self-sign.
