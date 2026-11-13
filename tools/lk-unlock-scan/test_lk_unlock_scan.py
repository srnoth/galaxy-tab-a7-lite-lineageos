import tempfile
import unittest
from pathlib import Path
from lk_unlock_scan import ANCHORS, SIGNATURES, find_signature, scan


def fixture(spec):
    tokens = spec.split()
    out = bytearray()
    i = 0
    while i < len(tokens):
        if tokens[i] == '??':
            out.extend(bytes.fromhex('00 f0 00 f8'))
            i += 4
        else:
            out.append(int(tokens[i], 16))
            i += 1
    return bytes(out)


class ScannerTests(unittest.TestCase):
    def classify(self, data):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'lk.img'
            p.write_bytes(data)
            return scan(p)

    def test_unknown_not_reported_as_unblocked(self):
        self.assertEqual(self.classify(b'\0' * 4096)['status'], 'INCONCLUSIVE')

    def test_generic_false_stub_alone_is_insufficient(self):
        self.assertEqual(self.classify(fixture(SIGNATURES['us_constant_false_gate']))['status'], 'INCONCLUSIVE')

    def test_all_us_patterns_and_context_detected_after_relocation(self):
        data = b'\0' * 202
        for name in ('us_constant_false_gate', 'us_startup_policy_sync', 'us_wipe_then_relock'):
            data += fixture(SIGNATURES[name]) + b'\0' * 16
        data += b'\0'.join(ANCHORS)
        self.assertEqual(self.classify(data)['status'], 'US_BLOCKER_SIGNATURES_DETECTED')

    def test_wildcard_bytes_must_be_actual_calls(self):
        spec = SIGNATURES['us_constant_false_gate']
        data = bytearray(fixture(spec)); data[6:10] = b'\0' * 4
        self.assertEqual(find_signature(data, spec), [])

    def test_conditional_gate_never_certifies_unblocked(self):
        data = fixture(SIGNATURES['xac_conditional_gate']) + b'\0'.join(ANCHORS)
        self.assertEqual(self.classify(data)['status'], 'XAC_STYLE_GATE_CANDIDATE')

    def test_compressed_image_rejected(self):
        self.assertEqual(self.classify(bytes.fromhex('04 22 4d 18') + b'\0' * 100)['status'], 'UNSUPPORTED_CONTAINER')

    def test_truncation_does_not_match(self):
        spec = SIGNATURES['xac_conditional_gate']
        self.assertEqual(find_signature(fixture(spec)[:-1], spec), [])


if __name__ == '__main__':
    unittest.main()
