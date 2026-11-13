#!/usr/bin/env python3
"""Read-only Samsung MTK LK reference/signature scanner; Python 3 standard library only."""
import argparse
import hashlib
import json
import re
from pathlib import Path

REFERENCES = {
    '1ef9d449c2876f9d23cbac9d3cef5168ccf66e07934e13083ee48b7641728dd9':
        ('BLOCKER_CONFIRMED', 'SM-T227U US T227USQSCEYE2', 'Blocking paths established by static trace; generic seccfg unlock did not persist in our test.'),
    '1c093c2e3f016ab587f78503c19cb8591691e227095f90907486b6c2eaca0f66':
        ('REFERENCE_UNLOCK_TESTED', 'SM-T227U XAC T227UVLSCFYE2', 'Known US blocker paths differ/are absent; LK replacement plus seccfg unlock succeeded on our SM-T227U. Not a universal safety claim.'),
}

# Thumb instruction signatures from the traced references, not strings or region tags.
# BL immediates are variable, but matches must contain real 32-bit Thumb BLs.
SIGNATURES = {
    'us_constant_false_gate': '00 b5 83 b0 01 a8 ?? ?? ?? ?? 00 20 03 b0 5d f8 04 fb',
    'us_startup_policy_sync': '09 98 ?? ?? ?? ?? 04 20 ?? ?? ?? ?? 18 b1 0a 9b 00 2b 40 f0 eb 80 04 20 ?? ?? ?? ?? 18 b9 0a 9b 00 2b 00 f0 d4 80',
    'us_wipe_then_relock': '?? ?? ?? ?? 00 28 6d d0 01 20 ?? ?? ?? ?? ?? ?? ?? ??',
    'xac_conditional_gate': '00 b5 83 b0 01 a8 ?? ?? ?? ?? 01 9b 01 20 13 b9 03 b0 5d f8 04 fb ?? ?? ?? ?? 00 28 f8 d0 ?? ?? ?? ?? b0 fa 80 f0 40 09 03 b0 5d f8 04 fb',
}
ANCHORS = [b'lock -> unlock', b'unlock -> lock', b'--reason=ChangeDeviceState', b'SEC_UNLOCK']


def find_signature(data, spec):
    tokens = spec.split()
    pattern = b''.join(b'.' if t == '??' else re.escape(bytes.fromhex(t)) for t in tokens)
    calls = [i for i, t in enumerate(tokens) if t == '??' and (i == 0 or tokens[i - 1] != '??')]
    # Some signatures have adjacent BL instructions: split every wildcard run in groups of four.
    calls = [j for i in calls for j in range(i, next((k for k in range(i, len(tokens)) if tokens[k] != '??'), len(tokens)), 4)]
    found = []
    for m in re.finditer(b'(?=(' + pattern + b'))', data, re.DOTALL):
        pos = m.start()
        if pos % 2:
            continue
        valid = True
        for off in calls:
            h1 = int.from_bytes(data[pos + off:pos + off + 2], 'little')
            h2 = int.from_bytes(data[pos + off + 2:pos + off + 4], 'little')
            if h1 & 0xf800 != 0xf000 or h2 & 0xd000 != 0xd000:
                valid = False
                break
        if valid:
            found.append(pos)
    return found


def scan(path):
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    result = {'file': str(path), 'bytes': len(data), 'sha256': sha,
              'status': 'INCONCLUSIVE', 'reference': None, 'evidence': {},
              'meaning': 'No reliable classification. Missing signatures do not prove absence of an unlock blocker.',
              'safe_to_flash': 'NOT_ASSESSED'}
    if data.startswith((b'\x04\x22\x4d\x18', b'\x02\x21\x4c\x18', b'PK\x03\x04', b'\x1f\x8b')) or (len(data) > 262 and data[257:262] == b'ustar'):
        result['status'] = 'UNSUPPORTED_CONTAINER'
        result['meaning'] = 'Extract and decompress LK first. Input must be raw lk.bin / lk-verified.img, not firmware TAR/ZIP/LZ4/GZIP.'
        return result
    hits = {name: find_signature(data, sig) for name, sig in SIGNATURES.items()}
    result['evidence'] = {name: [hex(n) for n in offsets] for name, offsets in hits.items() if offsets}
    result['context_strings_present'] = [a.decode() for a in ANCHORS if a in data]
    result['image_markers'] = sorted({s.decode() for s in re.findall(rb'(?:KNL|SRP)UB[0-9A-Z]{6}', data)})
    if sha in REFERENCES:
        result['status'], result['reference'], result['meaning'] = REFERENCES[sha]
    elif all(hits[k] for k in ('us_constant_false_gate', 'us_startup_policy_sync', 'us_wipe_then_relock')) and all(a in data for a in ANCHORS):
        result['status'] = 'US_BLOCKER_SIGNATURES_DETECTED'
        result['meaning'] = 'All three traced US-style code signatures and LK context found. Strong candidate for the same blocker; manually trace callers and targets to confirm on this build.'
    elif hits['xac_conditional_gate'] and all(a in data for a in ANCHORS) and not hits['us_startup_policy_sync']:
        result['status'] = 'XAC_STYLE_GATE_CANDIDATE'
        result['meaning'] = 'Conditional XAC-style gate found; known US startup signature not found. This does NOT prove the image lacks another blocker or that unlocking/flashing will work.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog="Never use another model's LK based on this output. This does not check signatures, rollback, fuses, KG policy, or hardware compatibility.")
    parser.add_argument('images', nargs='+', type=Path, help='Raw, decompressed LK images (multiple allowed)')
    parser.add_argument('--json', action='store_true', help='Machine-readable report')
    args = parser.parse_args()
    reports = []
    failed = False
    for path in args.images:
        try:
            reports.append(scan(path))
        except OSError as exc:
            reports.append({'file': str(path), 'status': 'READ_ERROR', 'error': str(exc)})
            failed = True
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for r in reports:
            print(f"{r['file']}: {r['status']}")
            if 'error' in r:
                print('  ' + r['error'])
                continue
            print(f"  SHA256: {r['sha256']}")
            if r['reference']:
                print('  Reference: ' + r['reference'])
            for name, offsets in r['evidence'].items():
                print(f"  {name}: {', '.join(offsets)}")
            print('  ' + r['meaning'])
        print('\nRead-only analysis. Flash safety/compatibility NOT assessed.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
