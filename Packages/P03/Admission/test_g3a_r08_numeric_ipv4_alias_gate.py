"""G3-A R30 R08: reject numeric IPv4 spellings that bypass ipaddress parsing.

Source-only tests of the original P03 policy; no network/DNS/download/native host.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p03_modelcenter_gate as gate


class NumericIPv4AliasAdmission(unittest.TestCase):
    def deny(self, url: str) -> None:
        self.assertFalse(gate._https_url(url), url)

    def allow(self, url: str) -> None:
        self.assertTrue(gate._https_url(url), url)

    def test_01_short_loopback_ipv4(self):
        self.deny("https://127.1/license")

    def test_02_hexadecimal_loopback_ipv4(self):
        self.deny("https://0x7f.1/license")

    def test_03_octal_loopback_ipv4(self):
        self.deny("https://0177.0.0.1/license")

    def test_04_all_hex_loopback_ipv4(self):
        self.deny("https://0x7f.0x0.0x0.0x1/license")

    def test_05_octal_private_ipv4(self):
        self.deny("https://0300.0250.1.1/license")

    def test_06_invalid_leading_zero_private_ipv4(self):
        self.deny("https://127.000.0.1/license")

    def test_07_canonical_loopback_remains_denied(self):
        self.deny("https://127.0.0.1/license")

    def test_08_official_https_library_still_allowed(self):
        self.allow("https://ollama.com/library/qwen3")

    def test_09_public_https_rights_still_allowed(self):
        self.allow("https://huggingface.co/example/rights")

    def test_10_public_global_ipv4_still_allowed(self):
        self.allow("https://8.8.8.8/license")


if __name__ == "__main__":
    unittest.main()
