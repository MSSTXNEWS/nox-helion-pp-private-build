"""Only SourceLock-reviewed discovery fields may be exposed to ModelCenter.
Run: python -m unittest -v test_p03_discovery_fields_r47
No Ollama, model downloads, Windows backend or external services.
"""
import json
import tempfile
import unittest
from pathlib import Path
from p03_onehost_port import P03OneHostPort, P03PortHold

CATALOG = Path(__file__).with_name("catalog30.discovery.json")

class DiscoveryFieldSchemaR47(unittest.TestCase):
    def load(self, extra=None):
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        if extra:
            data["models"][0].update(extra)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return P03OneHostPort._validate_catalog(path)

    def test_original_thirty_discovery_cards_remain_valid(self):
        cards = self.load()
        self.assertEqual(len(cards), 30)
        self.assertTrue(all(set(card) ==
            {"id", "name", "url", "reviewStatus", "downloadEligible"}
            and card["downloadEligible"] is False for card in cards))

    def test_unreviewed_license_assertion_cannot_leak_into_browser(self):
        with self.assertRaises(P03PortHold):
            self.load({"licenseVerified": True})

    def test_unreviewed_weights_source_cannot_leak_into_browser(self):
        with self.assertRaises(P03PortHold):
            self.load({"weightsUrl": "https://untrusted.example/model.gguf"})

if __name__ == "__main__":
    unittest.main()
