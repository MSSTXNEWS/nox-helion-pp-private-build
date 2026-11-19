import ast
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


MODULE = Path("nox_runpod/teacher_mesh/v129/read_native_s03_write_contract.py")


def load_remote_helpers():
    source = MODULE.read_text(encoding="utf-8")
    outer = ast.parse(source)
    remote_node = next(
        node.value
        for node in outer.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "REMOTE"
                for target in node.targets)
    )
    remote = ast.literal_eval(remote_node)
    marker = "python - <<'PYREMOTE'\n"
    script = remote.split(marker, 1)[1].split("\nPYREMOTE", 1)[0]
    tree = ast.parse(script)
    wanted_constants = {
        "MODULE_PATH", "MODULE_ROOT", "MODULE_ALLOWLIST", "MAX_SOURCE_BYTES",
        "WRITER_NAMES", "TABLE_ALLOWLIST",
    }
    wanted_functions = {
        "_hold", "_path_no_symlinks", "_read_allowlisted_source", "_safe_type",
        "_writer_contract", "_eval_path_expr", "_database_path", "_schema_snapshot",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            nodes.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in wanted_constants
            for target in node.targets
        ):
            nodes.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted_functions:
            nodes.append(node)
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<remote-audit-helpers>", "exec"), namespace)
    return namespace


class ReadNativeS03WriterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = load_remote_helpers()

    def test_symlink_and_out_of_root_module_paths_hold(self):
        read_source = self.helpers["_read_allowlisted_source"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            root.mkdir()
            scripts = root / "scripts"
            scripts.mkdir()
            outside = Path(temp) / "outside.py"
            outside.write_text("def remember(): pass\n", encoding="utf-8")
            alias = scripts / "s03_memory.py"
            alias.symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError, "HOLD_S03_PATH_SYMLINK"):
                read_source(alias, (alias,), root, 1000)
            with self.assertRaisesRegex(RuntimeError, "HOLD_S03_PATH_OUTSIDE_ROOT"):
                read_source(outside, (outside,), root, 1000)

    def test_missing_and_oversized_source_hold(self):
        read_source = self.helpers["_read_allowlisted_source"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            scripts = root / "scripts"
            scripts.mkdir(parents=True)
            missing = scripts / "missing.py"
            with self.assertRaisesRegex(RuntimeError, "HOLD_S03_PATH_MISSING|HOLD_S03_SOURCE_MISSING"):
                read_source(missing, (missing,), root, 16)
            oversized = scripts / "s03_memory.py"
            oversized.write_bytes(b"x" * 17)
            with self.assertRaisesRegex(RuntimeError, "HOLD_S03_SOURCE_SIZE"):
                read_source(oversized, (oversized,), root, 16)

    def test_database_schema_inspection_is_read_only_and_never_returns_rows(self):
        inspect_schema = self.helpers["_schema_snapshot"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            db_path = root / "knowledge.sqlite"
            secret = "PRIVATE_DIALOG_SENTINEL_8b7e4e"
            with sqlite3.connect(db_path) as con:
                con.execute("CREATE TABLE s03_items (id TEXT PRIMARY KEY, text TEXT, sha256 TEXT)")
                con.execute("CREATE INDEX idx_s03_sha ON s03_items(sha256)")
                con.execute("INSERT INTO s03_items VALUES(?,?,?)", ("row-1", secret, "a" * 64))
            before = hashlib.sha256(db_path.read_bytes()).hexdigest()
            result = inspect_schema(db_path, root, ("s03_items", "s03_ledger"))
            encoded = json.dumps(result, sort_keys=True)
            self.assertTrue(result["read_only"])
            self.assertFalse(result["private_rows_exported"])
            self.assertIn("idx_s03_sha", encoded)
            self.assertIn('"name": "text"', encoded)
            self.assertNotIn(secret, encoded)
            self.assertEqual(hashlib.sha256(db_path.read_bytes()).hexdigest(), before)
            with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as con:
                with self.assertRaises(sqlite3.OperationalError):
                    con.execute("INSERT INTO s03_items VALUES(?,?,?)", ("row-2", "x", "b" * 64))

    def test_signature_report_contains_only_allowlisted_ast_metadata(self):
        contract = self.helpers["_writer_contract"]
        raw = b"def remember(text: str, segment='M2') -> dict[str, str]:\n    return {'secret': text}\n"
        result = contract(raw)
        encoded = json.dumps(result, sort_keys=True)
        self.assertIn('"name": "remember"', encoded)
        self.assertIn('"return_type": "dict[str, str]"', encoded)
        self.assertNotIn("secret", encoded)
        self.assertNotIn("return", encoded)


if __name__ == "__main__":
    unittest.main()
