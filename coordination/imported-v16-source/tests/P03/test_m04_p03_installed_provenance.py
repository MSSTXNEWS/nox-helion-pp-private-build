"""M04: Ollama /api/tags presence is NOT verified installed weight SHA.

Run: python -m unittest discover -s tests/P03 -p test_m04_p03_installed_provenance.py -v
No Ollama process, network access, model downloads or UI startup required.
"""
import importlib.util
import pathlib
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Packages/P03/Source/python-host/p03_onehost_port.py"

spec = importlib.util.spec_from_file_location("nox_m04_p03_provenance", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class FakeOllama:
    def __init__(self):
        self.reads = 0
    def models(self):
        self.reads += 1
        return ["qwen2.5-coder:1.5b"]

class InstalledProvenanceTest(unittest.TestCase):
    def test_tags_are_not_hashed_installed_weights(self):
        port = object.__new__(module.P03OneHostPort)
        port.ollama = FakeOllama()
        session = types.SimpleNamespace(tenant="local", principal="owner",
            chat_id="chat", allowed={"models.installed"})
        snapshot = port.installed(session, {})
        self.assertEqual(port.ollama.reads, 1)
        self.assertEqual(snapshot["models"], [{
            "tag": "qwen2.5-coder:1.5b", "installed": False,
            "ollamaReportedPresent": True, "digest": None,
        }])
        self.assertIs(snapshot["digestVerified"], False)
        self.assertNotIn("licenseVerified", snapshot)

if __name__ == "__main__":
    unittest.main()
