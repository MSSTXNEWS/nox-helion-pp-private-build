"""T06 original installed same-VM proof: fail-closed JSON and receipt gate.

Source-level tests only; never attest native Windows GUI, Setup or independent E07.
"""
from __future__ import annotations
import ast
import json
import math
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "coordination/e06/t06_samevm_installed_smoke.py"


def load_source_gates():
    # This entrypoint runs a real Windows install at module execution.
    # Compile only actual function AST nodes to test without side effects.
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    selected = [node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name in (
                    "require", "regular", "strict_json_object", "strict_receipt")]
    names = {node.name for node in selected}
    if names != {"require", "regular", "strict_json_object", "strict_receipt"}:
        raise AssertionError("T06_STRICT_INSTALLED_JSON_GATES_MISSING")
    context = {"json": json, "math": math, "Path": Path}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), context)
    return context["strict_json_object"], context["strict_receipt"]


class InstalledProofJsonGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        decoder, reader = load_source_gates()
        cls.decode = staticmethod(decoder)
        cls.receipt = staticmethod(reader)

    def test_valid_native_ack_and_receipt(self):
        good = b'{"protocol":"NOX-P02-NATIVE-v1","status":"OK","result":{"models":[]}}'
        self.assertEqual(self.decode(good, "HOLD")["status"], "OK")
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "receipt.json"
            file.write_bytes(good)
            self.assertEqual(self.receipt(file, "HOLD")["status"], "OK")

    def test_top_level_and_nested_duplicate_keys_hold(self):
        bad = (b'{"status":"HOLD","status":"OK"}',
               b'{"result":{"models":[],"models":["fake"]}}',
               b'{"phase":"FAILED","phase":"PASS"}')
        for data in bad:
            with self.subTest(length=len(data)), self.assertRaisesRegex(RuntimeError, "^HOLD$"):
                self.decode(data, "HOLD")

    def test_nan_infinity_and_overflow_hold(self):
        for data in (b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}',
                     b'{"x":1e999}', b'{"x":-1e999}'):
            with self.subTest(length=len(data)), self.assertRaisesRegex(RuntimeError, "^HOLD$"):
                self.decode(data, "HOLD")

    def test_invalid_bytes_nonobject_and_oversized_hold(self):
        for data in (b'{"x":\xff}', b'[]', b'null', b'{}{}',
                     b'{"x":"' + b"A" * 1048576 + b'"}'):
            with self.subTest(length=len(data)), self.assertRaisesRegex(RuntimeError, "^HOLD$"):
                self.decode(data, "HOLD")

    def test_receipt_redirect_duplicate_and_size_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "receipt.json"
            file.write_bytes(b'{"phase":"FAILED","phase":"PASS"}')
            with self.assertRaisesRegex(RuntimeError, "^HOLD$"):
                self.receipt(file, "HOLD")
            file.write_bytes(b'{"ok":true}')
            link = Path(directory) / "link.json"
            try:
                link.symlink_to(file)
            except (OSError, NotImplementedError):
                pass  # Windows developer mode may not permit symlinks.
            else:
                with self.assertRaisesRegex(RuntimeError, "^HOLD$"):
                    self.receipt(link, "HOLD")
            file.write_bytes(b"A" * (4 * 1024 * 1024 + 1))
            with self.assertRaisesRegex(RuntimeError, "^HOLD$"):
                self.receipt(file, "HOLD")

    def test_real_original_wiring_not_a_mock_parser(self):
        source = SOURCE.read_text("utf-8")
        self.assertEqual(source.count("strict_receipt("), 9)  # helper + eight readers
        self.assertEqual(source.count("json.loads("), 1)  # only strict decoder
        self.assertIn('answer=strict_json_object(content[4:]', source)
        self.assertNotIn('json.loads(content[4:].decode("utf-8"))', source)


if __name__ == "__main__":
    unittest.main()
