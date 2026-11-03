# SPDX-License-Identifier: GPL-2.0-only
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from catalog import PROFESSIONAL, by_device, load_cards, selector_ok  # noqa: E402


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.cards = by_device()

    def test_table_loads_without_duplicates(self):
        self.assertGreaterEqual(len(load_cards()), 100)

    def test_rtx_4070_ad104_is_family_supported(self):
        card = self.cards["2786"]
        self.assertEqual(card["chip"], "0x194")
        self.assertEqual(card["confidence"], "family")
        self.assertIn("4070", card["name"])
        self.assertIn("AD104", card["name"])

    def test_4070_ti_is_the_validated_ad104_sibling(self):
        card = self.cards["2782"]
        self.assertEqual(card["chip"], "0x194")
        self.assertEqual(card["confidence"], "validated")

    def test_ad103_4070_variant_is_present(self):
        self.assertEqual(self.cards["2709"]["confidence"], "family")
        self.assertEqual(self.cards["2709"]["chip"], "0x193")

    def test_4070_laptop_is_experimental_and_not_ad104(self):
        card = self.cards["2820"]
        self.assertEqual(card["confidence"], "experimental")
        self.assertEqual(card["chip"], "0x196")
        self.assertIn("2860", self.cards)

    def test_restored_ga106_laptop_ids(self):
        for device in ("2520", "2521", "2560", "2561"):
            self.assertEqual(self.cards[device]["confidence"], "family")
            self.assertEqual(self.cards[device]["chip"], "0x176")

    def test_ga107_uses_the_documented_chip_id_and_stays_experimental(self):
        card = self.cards["2582"]
        self.assertEqual(card["chip"], "0x177")
        self.assertEqual(card["confidence"], "experimental")
        self.assertIn("25a5", self.cards)

    def test_professional_and_unknown_ids_are_absent(self):
        for device in list(PROFESSIONAL) + ["25af", "25b6", "25be", "25f9", "2822"]:
            self.assertNotIn(device, self.cards)

    def test_turing_stays_experimental(self):
        self.assertEqual(self.cards["1e04"]["confidence"], "experimental")

    def test_selector_encodings(self):
        self.assertTrue(selector_ok(0x88888888, 8))
        self.assertTrue(selector_ok(0x8, 1))
        self.assertTrue(selector_ok(0x1, 8))
        self.assertTrue(selector_ok(0x1, 1))
        self.assertTrue(selector_ok(0x99999999, 8))
        self.assertFalse(selector_ok(0x2, 1))
        self.assertFalse(selector_ok(0x88888882, 8))
        self.assertFalse(selector_ok(0x18, 1))

    def test_policy_source_uses_the_same_nibbles(self):
        text = (ROOT / "kernel" / "gpu_unlock" / "policy.c").read_text()
        for nibble in ("0x0", "0x1", "0x8", "0x9"):
            self.assertIn(f"case {nibble}:", text)
        self.assertNotIn("case 0x2:", text)
        self.assertNotIn("case 0x3:", text)

    def test_input_hashes_match_the_package_pins(self):
        fetch = (ROOT / "firmware" / "fetch_artifacts.py").read_text()
        spec = (ROOT / "packaging" / "rpm" / "gpu-unlock.spec").read_text()
        pkgbuild = (ROOT / "packaging" / "arch" / "PKGBUILD").read_text()
        hashes = re.findall(r'"sha256": "([0-9a-f]{64})"', fetch)
        self.assertEqual(len(hashes), 2)
        for digest in hashes:
            self.assertIn(digest, spec)
            self.assertIn(digest, pkgbuild)


class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "tools" / "teraflix.py"), *args],
            check=False, capture_output=True, text=True,
        )

    def test_list_mentions_the_4070(self):
        result = self.run_cli("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2786", result.stdout)
        self.assertIn("family", result.stdout)
        self.assertNotIn("24b0", result.stdout)

    def test_explain_professional_card(self):
        result = self.run_cli("explain", "24b0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("A4000", result.stdout)
        self.assertIn("full tensor rate", result.stdout)

    def test_explain_4070(self):
        result = self.run_cli("explain", "2786")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0x194", result.stdout)
        self.assertIn("family", result.stdout)

    def test_require_missing_device_fails(self):
        result = self.run_cli("check", "--require", "2786")
        self.assertNotEqual(result.returncode, 0)

    def test_check_runs_without_a_gpu(self):
        result = self.run_cli("check")
        self.assertEqual(result.returncode, 0, result.stderr)


class BenchmarkTest(unittest.TestCase):
    def test_self_test(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "benchmark.py"), "--self-test"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
