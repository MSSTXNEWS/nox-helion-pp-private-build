"""R47/P03 native installed-model readiness must not falsely advertise malformed tags.

Tests REAL p03_onehost_port in the same source directory, without Ollama, weights,
network, filesystem writes, or any native Windows host calls.
Run: python -m unittest -v test_p03_installed_readiness_r47
"""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortHold

class InstalledReadinessR47(unittest.TestCase):
    @staticmethod
    def port(tags):
        p = object.__new__(P03OneHostPort)
        p.ollama = SimpleNamespace(models=lambda: tags)
        return p

    @staticmethod
    def session():
        return SimpleNamespace(tenant="t", principal="p", chat_id="c",
                               allowed=frozenset({"models.installed"}))

    def test_valid_tags_still_ready(self):
        p = self.port(["qwen3:4b", "tinyllama:1.1b"])
        self.assertTrue(p._local_ready())
        self.assertEqual(len(p.installed(self.session(), {})["models"]), 2)

    def test_invalid_tag_not_advertised(self):
        p = self.port(["untrusted tag"])
        self.assertFalse(p._local_ready())
        with self.assertRaises(P03PortHold):
            p.installed(self.session(), {})

    def test_duplicate_tags_not_advertised(self):
        p = self.port(["qwen3:4b", "qwen3:4b"])
        self.assertFalse(p._local_ready())
        with self.assertRaises(P03PortHold):
            p.installed(self.session(), {})

    def test_oversized_tags_response_not_advertised(self):
        p = self.port(["m" + str(i) for i in range(4097)])
        self.assertFalse(p._local_ready())
        with self.assertRaises(P03PortHold):
            p.installed(self.session(), {})

if __name__ == "__main__": unittest.main()
