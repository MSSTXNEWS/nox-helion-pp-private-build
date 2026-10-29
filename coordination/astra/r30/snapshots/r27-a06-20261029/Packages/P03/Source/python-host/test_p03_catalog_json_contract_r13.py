"""P03 R13: malformed discovery JSON must HOLD; no downloader, weights or network."""
import json
import tempfile
import unittest
from pathlib import Path

from p03_onehost_port import P03OneHostPort, P03PortHold


def fixture():
    return {"schema": "NOX-P03-PYTHON-ONEHOST-CATALOG-V1",
            "sourceType": "discovery_only",
            "models": [{"id": f"model-{i}", "name": f"Model {i}",
                        "url": f"https://ollama.com/library/model-{i}",
                        "reviewStatus": "REVIEW_REQUIRED", "downloadEligible": False}
                       for i in range(30)]}


class CatalogJsonContractR13(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "catalog30.discovery.json"

    def tearDown(self):
        self.tmp.cleanup()

    def hold(self, raw):
        self.path.write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        with self.assertRaises(P03PortHold):
            P03OneHostPort._validate_catalog(self.path)

    def test_01_valid_discovery_remains_readonly(self):
        self.path.write_text(json.dumps(fixture()), encoding="utf-8")
        cards = P03OneHostPort._validate_catalog(self.path)
        self.assertEqual(len(cards), 30)
        self.assertTrue(all(card["downloadEligible"] is False for card in cards))

    def test_02_scalar_or_list_json_root_holds(self):
        for raw in ("null", "[]", "true", '"scalar"', "19"):
            with self.subTest(root=raw):
                self.hold(raw)

    def test_03_duplicate_schema_key_holds(self):
        self.hold(json.dumps(fixture()).replace('"schema":',
                   '"schema": "OTHER", "schema":', 1))

    def test_04_duplicate_download_eligibility_holds(self):
        self.hold(json.dumps(fixture()).replace('"downloadEligible": false',
                  '"downloadEligible": true, "downloadEligible": false', 1))

    def test_05_nan_numeric_literal_holds(self):
        self.hold(json.dumps(fixture()).replace('"sourceType":',
                  '"value": NaN, "sourceType":', 1))

    def test_06_bad_utf8_holds(self):
        self.hold(b"\xff\xfe")

    def test_07_malformed_json_holds(self):
        self.hold('{"models":')

    def test_08_array_of_cards_holds(self):
        self.hold(json.dumps(fixture()["models"]))

    def test_09_existing_symlink_holds(self):
        target = Path(self.tmp.name) / "other.json"
        target.write_text(json.dumps(fixture()), encoding="utf-8")
        try:
            self.path.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("OS does not permit symlink creation")
        with self.assertRaises(P03PortHold):
            P03OneHostPort._validate_catalog(self.path)


if __name__ == "__main__":
    unittest.main()
