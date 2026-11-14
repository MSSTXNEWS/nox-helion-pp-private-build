"""NOX V16 WOW 001-200 source-catalog integrity (no native acceptance).

Run: python -m unittest discover -s tests/e06 -p 'test_wow200_catalog_integrity_r02.py' -v
The source catalogs intentionally hold privileged routes until owner-native ACK.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WOW = ROOT / "integrations" / "wow200" / "proposals"


def load_js_json_array(path):
    text = path.read_text(encoding="utf-8")
    marker = "Object.freeze(["
    start = text.find(marker)
    if start < 0:
        raise ValueError("MISSING_IMMUTABLE_CATALOG")
    start = text.find("[", start)
    end = text.find("].map(", start)
    if end < 0:
        raise ValueError("CATALOG_ARRAY_END_MISSING")
    return json.loads(text[start:end + 1])


class Wow200CatalogSourceIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads(
            (ROOT / "proposals" / "NOX-PACK01-50" / "catalog.json")
            .read_text(encoding="utf-8")
        )["actions"]
        cls.cues = load_js_json_array(WOW / "NOX-WOW51-100" / "catalog.mjs")
        cls.shots = load_js_json_array(WOW / "NOX-WOW101-150" / "catalog.mjs")
        cls.finales = load_js_json_array(WOW / "NOX-WOW151-200" / "catalog.mjs")

    def test_exact_counts_and_contiguous_ids(self):
        for group, begin in [
            (self.pack, 1), (self.cues, 51),
            (self.shots, 101), (self.finales, 151),
        ]:
            with self.subTest(start=begin):
                self.assertEqual(len(group), 50)
                if begin > 1:
                    self.assertEqual([x["id"] for x in group], list(range(begin, begin + 50)))

    def test_source_route_registry_has_no_fake_actions(self):
        self.assertEqual(len({x["routeId"] for x in self.pack}), 50)
        self.assertEqual(len({x["taskId"] for x in self.pack}), 50)
        self.assertEqual(
            [x["taskId"] for x in self.pack],
            [f"NIP01-{i:02d}" for i in range(1, 51)],
        )
        self.assertTrue(all(x["intent"] == "nox.feature.request" for x in self.pack))

    def test_original_cues_source_hold(self):
        self.assertTrue(all(
            x["acceptance"] == "SOURCE_CANDIDATE_NOT_EXE"
            and x["scope"] == "APPROVED_SECONDARY_ONLY"
            for x in self.cues
        ))

    def test_finales_use_only_existing_sub_effects(self):
        ids51 = {x["id"] for x in self.cues}
        ids101 = {x["id"] for x in self.shots}
        self.assertTrue(all(
            x["directorId"] in ids101 and x["opticalId"] in ids51
            and x["opticalId"] not in set(range(81, 91))
            for x in self.finales
        ))

    def test_finales_are_source_only(self):
        self.assertTrue(all(
            x["status"] == "SOURCE_COMPONENT"
            and x["scope"] == "APPROVED_SECONDARY_ONLY"
            for x in self.finales
        ))

    def test_no_duplicate_secondary_ids(self):
        ids = [x["id"] for x in (*self.cues, *self.shots, *self.finales)]
        self.assertEqual(len(ids), 150)
        self.assertEqual(len(set(ids)), 150)
        self.assertEqual(ids, list(range(51, 201)))


if __name__ == "__main__":
    unittest.main()
