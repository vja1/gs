import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import captcha_solver


SAMPLES = [
    ("samples/s01.jpg", "13BOKJ"),
    ("samples/s02.jpg", "KQ2BQQ"),
    ("samples/s08.jpg", "XA5Q1E"),
    ("samples/s03.jpg", "WYCBTD"),
]


class SolverTests(unittest.TestCase):
    def test_reads_blue_captcha_samples(self):
        hits = 0
        for name, expected in SAMPLES:
            path = ROOT / name
            if not path.exists():
                self.skipTest("sample captchas missing")
            readings = captcha_solver.solve(path.read_bytes())
            if readings and readings[0][0] == expected:
                hits += 1
        self.assertGreaterEqual(hits, 2, "solver should read most samples")

    def test_digit_charset_maps_lookalikes(self):
        self.assertEqual(captcha_solver.normalise("O1SB2Z", captcha_solver.DIGITS), "015822")
        self.assertEqual(captcha_solver.normalise("abcd", captcha_solver.DIGITS), "480")
        self.assertEqual(captcha_solver.normalise("", captcha_solver.DIGITS), "")

    def test_letter_charset_keeps_letters(self):
        self.assertEqual(captcha_solver.normalise("ab12", captcha_solver.ALLOWED), "AB12")


if __name__ == "__main__":
    unittest.main()
