# Samsung Galaxy Tab A7 Lite (`gta7lite`) on LineageOS

Everything I've learned running a **Samsung Galaxy Tab A7 Lite** on a **LineageOS 21 (Android 14) GSI** —
the firmware conversion, the fixes the GSI needs afterwards, and the hardware quirks that aren't written
down anywhere else.

Every fix here was **validated on real hardware**, not copied from a forum. Where something is unverified,
it says so.

---

## The device

| | |
|---|---|
| Marketing name | Samsung Galaxy Tab A7 Lite |
| Device codename | `gta7lite` (LTE) · `gta7litewifi` (Wi-Fi, SM-T220) |
| Models | **SM-T227U** (US carrier, LTE) · SM-T225 (intl LTE) · SM-T220 (Wi-Fi) |
| SoC | MediaTek **MT8768T** / `mt6765` — 8× Cortex-A53 |
| GPU | PowerVR GE8320 (**not** Mali — device-targeted MTK GPU mods often assume Mali) |
| RAM | 3 GB |
| Display | 8.7", LCD, 60 Hz, 800×1340 |
| Ambient light sensor | **AMS `tsl2540`** — present, and *works*, but the GSI disables it (see below) |
| Proximity sensor | **None** |
| Fingerprint sensor | **None** |

---

## What's here

The guide is in three tiers. **Tier 1 alone gets you a fully working tablet** — the rest is opt-in.

### 1️⃣ 📘 [Conversion playbook](docs/conversion-playbook.md) — the whole flash procedure
US-carrier **SM-T227U** → Canadian **XAC** firmware → **LineageOS GSI**. Bootloader unlock via
mtkclient/BROM, TWRP, the GSI flash, and the **boot-image SPL match that fixes the lockscreen PIN loop**
(set a PIN on a stock GSI and you get locked out in a blank-screen loop — this is why). Also covers updating
to a newer LineageOS build later. Drivable by hand or by an LLM agent; every gotcha was hit on real hardware.

### 2️⃣ 🔓 [Optional: root with Magisk](docs/conversion-playbook.md#2b-optional--root-with-magisk)
Not needed for anything in tier 1. You want it only if you're going to use tier 3. The one thing to get
right: patch the **SPL-matched** boot from Phase 5, not the stock boot, or you land back in the PIN loop.

### 3️⃣ 💡 [Optional: Magisk tweaks](docs/conversion-playbook.md#2c-optional--magisk-tweaks)
Small, systemless, individually toggleable — nothing modifies `/system`.
- **[Adaptive brightness](magisk/gta7lite-autobrightness/)** — the GSI ships it **hard-disabled** even though
  this tablet has a working ambient light sensor. One boolean fixes it. ~8 KB, and it deliberately does
  **not** ship a brightness curve, because Samsung's factory-tuned curve is still on your tablet and is
  better than anything you'd write by hand.

### 🔧 [Post-install fixes & tweaks](docs/post-install-tweaks.md) — no root required
- **Screen turns itself on in an endless loop** when the lockscreen is set to "None" — a genuine
  LineageOS/AOSP bug (not a GSI quirk), with a one-command fix. **Bites kiosk builds especially**, because
  Fully Kiosk's own "disable lockscreen" re-triggers it.
- **Airplane mode that kills only the modem**, leaving Wi-Fi up — silences a SIM-less LTE tablet's constant
  modem scanning.
- A full, opinionated **review of every phh/TrebleDroid Treble Settings option** on this device: what's worth
  trying, what physically cannot work, and the ones that can wreck your install.
- **Hardware notes** — which sensors exist, which don't, and what that rules out.

---

## The single most useful thing I learned

**A GSI only replaces `/system`. Your stock Samsung `/vendor` is still there — and so are its resources.**

Before you hand-author *any* device resource for a GSI, go look at what the factory already gave you:

```bash
adb root
adb pull /vendor/overlay/FrameworkResOverlay/FrameworkResOverlay.apk
apktool d FrameworkResOverlay.apk
```

That's how the adaptive-brightness fix went from "invent a lux→backlight curve and hope" to "flip one
boolean and let Samsung's own tuned curve run." I got it wrong first. Check `/vendor` first.

---

## Contributing / accuracy

If something here is wrong, or works differently on `gta7litewifi` / SM-T225, open an issue. I only own
SM-T227U units, so that's the only variant anything here is *proven* on.

## License

[MIT](LICENSE). Firmware blobs are **not** redistributed here — the playbook tells you where to get them.
