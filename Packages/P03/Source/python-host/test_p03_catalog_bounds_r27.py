"""Real catalogue parsing and existing Ollama readiness share validity rules."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from p03_onehost_port import P03OneHostPort, P03PortHold
from test_p03_catalog_json_contract_r13 import fixture


class CatalogBoundsR27(unittest.TestCase):
    def test_catalog_numeric_overflow_holds(self):
        raw = json.dumps(fixture()).replace('"sourceType":', '"extra":1e999,"sourceType":', 1)
        self.assert_catalog_holds(raw)

    def test_deep_catalog_holds_without_recursion_exception(self):
        self.assert_catalog_holds('[' * 2000 + '0' + ']' * 2000)

    def test_long_json_integer_holds_without_value_exception(self):
        self.assert_catalog_holds('{"number":' + '1' * 5000 + '}')

    def test_catalog_read_size_enforced_after_stat(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'catalog.json'
            path.write_text(json.dumps(fixture()) + ' ' * 100001)
            real = path.stat(); values = list(real); values[6] = 64
            with patch.object(Path, 'stat', return_value=os.stat_result(values)):
                with self.assertRaises(P03PortHold):
                    P03OneHostPort._validate_catalog(path)

    def test_malformed_installed_evidence_never_advertised_ready(self):
        for values in ([42], ['qwen3:4b', 'qwen3:4b'], ['bad tag'], ['a'] * 4097):
            port = object.__new__(P03OneHostPort)
            port.ollama = SimpleNamespace(models=lambda: values, _open=lambda p: None)
            with self.subTest(values=values[:3]):
                self.assertFalse(port._local_ready())
                self.assertFalse(port._metadata_ready())

    def test_valid_empty_and_installed_lists_ready(self):
        for values in ([], ['qwen3:4b']):
            port = object.__new__(P03OneHostPort)
            port.ollama = SimpleNamespace(models=lambda: values)
            self.assertTrue(port._local_ready())

    def assert_catalog_holds(self, raw):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'catalog.json'
            path.write_text(raw)
            with self.assertRaises(P03PortHold):
                P03OneHostPort._validate_catalog(path)


if __name__ == '__main__': unittest.main()
