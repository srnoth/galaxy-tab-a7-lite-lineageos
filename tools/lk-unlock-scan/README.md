# Samsung MediaTek LK unlock-blocker scanner

A read-only Python 3 scanner for comparing raw, decompressed LK images from
the Galaxy Tab A7 Lite family. It uses only the Python standard library; it
does not modify images, need root, or communicate with a tablet.

```bash
python3 lk_unlock_scan.py US-lk.bin XAC-lk-verified.img
python3 lk_unlock_scan.py --json images/*.img > report.json
```

On Windows, use `py -3` instead of `python3` if necessary.

## Results

| Result | Meaning |
| --- | --- |
| `BLOCKER_CONFIRMED` | Exact hash of the traced US SM-T227U T227USQSCEYE2 LK. |
| `REFERENCE_UNLOCK_TESTED` | Exact hash of the XAC SM-T227U T227UVLSCFYE2 LK used in the documented one-device result. |
| `US_BLOCKER_SIGNATURES_DETECTED` | Three US-style instruction signatures plus context strings found; manually trace callers and targets to confirm. |
| `XAC_STYLE_GATE_CANDIDATE` | Conditional gate matches XAC-style code, but other blockers may exist. |
| `INCONCLUSIVE` | No reliable classification; this does not mean unblocked. |
| `UNSUPPORTED_CONTAINER` | Extract/decompress the firmware or LK first. |

Output contains SHA-256 values and file offsets, not runtime addresses. Exit 0
only means reports were generated, not that an image is unlockable.

## Input and safety limits

Prefer a readback of the device's `lk` partition, or extract
`lk-verified.img.lz4` from its own model's original Samsung BL tar.md5, then
decompress it before scanning. Do not pass a BL archive, ZIP, compressed LZ4
stream, boot image, or preloader.

Never flash an SM-T227U LK onto a T220, T225, or another model based on this
scanner. It does not assess secure-boot signature acceptance, rollback, KG or
fuse state, preloader compatibility, hardware compatibility, or reversibility.
An apparently favorable candidate is a reason for further tracing, not
permission to flash.

The US reference has a Download Mode gate that reads lock state then returns
false, plus a startup policy block that can request a wipe/relock. The XAC
reference has a conditional gate and lacks that particular startup block.
These observations come from static Thumb disassembly and one tablet's unlock
experiment. The scanner searches the entire file, so signatures can move, but
compiler/layout changes can evade detection and a match can be unreachable.

## Tests

```bash
python3 -m unittest discover -s . -p 'test_*.py' -v
```

The tests cover unknown data, insufficient evidence, relocation, valid call
encodings, truncated inputs, compressed containers, and conservative XAC
candidate output. Reference binaries and private backups are not included.
