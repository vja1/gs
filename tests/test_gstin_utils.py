import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gstin_utils


class ValidateTests(unittest.TestCase):
    def test_accepts_valid_gstin(self):
        self.assertEqual(gstin_utils.validate("27AAACT2727Q1ZW"), (True, ""))

    def test_normalises_case_and_spaces(self):
        self.assertTrue(gstin_utils.validate(" 27aaact2727q1zw ")[0])

    def test_rejects_bad_checksum(self):
        valid, reason = gstin_utils.validate("27AAACT2727Q1ZX")
        self.assertFalse(valid)
        self.assertIn("Checksum", reason)

    def test_rejects_unknown_state(self):
        gstin = "88" + "27AAACT2727Q1ZW"[2:14]
        gstin += gstin_utils.checksum_char(gstin)
        valid, reason = gstin_utils.validate(gstin)
        self.assertFalse(valid)
        self.assertIn("state", reason)

    def test_rejects_short_and_empty(self):
        self.assertFalse(gstin_utils.validate("27AAACT")[0])
        self.assertFalse(gstin_utils.validate("")[0])

    def test_state_lookup(self):
        self.assertEqual(gstin_utils.state_of("27AAACT2727Q1ZW"), "Maharashtra")

    def test_checksum_roundtrip(self):
        body = "27AAACT2727Q1Z"
        self.assertEqual(gstin_utils.checksum_char(body), "W")


if __name__ == "__main__":
    unittest.main()
