"""Focused offline executable contract for S1 GGUF staging (2A03).

This only extracts and tests the already-existing worker code. It never
executes the launcher, accesses Vast, contacts Hugging Face or modifies weights.
"""
import ast
import contextlib
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parent / "c100" / "glm_redo_s1.sh"


def worker_source():
    shell = SCRIPT.read_text(encoding="utf-8")
    opening = "cat > /root/nox/redo_worker.py <<'W'\n"
    assert shell.count(opening) == 1, "missing or duplicated worker heredoc"
    body, rest = shell.split(opening, 1)[1].split("\nW\n", 1)
    assert "PENDING_GGUF_SHA" in rest
    return body, shell


def isolated_worker_node(tree, name):
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.If))
             and ((isinstance(node, ast.FunctionDef) and node.name == name)
                  or (name == "__mixed_hold__" and isinstance(node, ast.If)
                      and "not all(results)" in ast.unparse(node.test)))]
    assert len(nodes) == 1, (name, len(nodes))
    return compile(ast.fix_missing_locations(ast.Module(
        body=nodes, type_ignores=[])), "<2A03-worker>", "exec")


class GGUFSourceContracts(unittest.TestCase):
    def test_shell_and_embedded_worker_parse(self):
        body, shell = worker_source()
        check = subprocess.run(["bash", "-n", str(SCRIPT)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, check=False, timeout=10)
        self.assertEqual(check.returncode, 0, check.stderr)
        compile(body, "<redo_worker.py>", "exec")
        self.assertIn('run_id="$(date -u', shell)
        self.assertIn('-$$"', shell)
        self.assertIn('immutable_snapshot": False', body)
        self.assertIn('owner_prepublish_sha_inode_recheck_required', body)

    def test_mixed_verified_and_missing_shards_emit_hold_not_typeerror(self):
        tree = ast.parse(worker_source()[0])
        code = isolated_worker_node(tree, "__mixed_hold__")
        scope = {"results": ["/verified/one.gguf", False], "names": ["a.gguf", "b.gguf"], "sys": sys}
        capture = io.StringIO()
        with contextlib.redirect_stdout(capture), self.assertRaises(SystemExit) as raised:
            exec(code, scope)
        self.assertEqual(raised.exception.code, 3)
        self.assertIn("HOLD_GGUF_NOT_ALL_VERIFIED 1 of 2", capture.getvalue())

    def test_interrupted_part_is_resumed_and_reused_without_touching_live(self):
        tree = ast.parse(worker_source()[0])
        with tempfile.TemporaryDirectory() as folder:
            name = "GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf"
            data = b"verified shard payload" * 1024
            oid = hashlib.sha256(data).hexdigest()
            manifest = hashlib.sha256(b"pinned-manifest-fixture").hexdigest()
            partial = Path(folder) / ".nox_verified" / manifest / (name + ".part")
            partial.parent.mkdir(parents=True)
            cut = len(data) // 3
            partial.write_bytes(data[:cut])
            calls = []

            def download(args, **kwargs):
                self.assertEqual(args[args.index("-C") + 1], "-")
                self.assertEqual(args[args.index("-o") + 1], str(partial))
                calls.append(partial.stat().st_size)
                with partial.open("ab") as out:
                    out.write(data[partial.stat().st_size:])
                return types.SimpleNamespace(returncode=0)

            def digest(path):
                return hashlib.sha256(Path(path).read_bytes()).hexdigest()

            scope = {"os": os, "subprocess": subprocess, "sys": sys,
                     "meta": {name: (len(data), oid)}, "MANIFEST_SHA": manifest,
                     "place": lambda _: folder, "sha": digest, "BASE": "fixture://",
                     "cgroup_admitted": lambda extra_bytes=0: True}
            exec(isolated_worker_node(tree, "verified"), scope)
            exec(isolated_worker_node(tree, "one"), scope)
            ample_disk = types.SimpleNamespace(f_bavail=1 << 30, f_frsize=4096)
            with (mock.patch.object(os, "statvfs", return_value=ample_disk),
                 mock.patch.object(subprocess, "run", side_effect=download)):
                staged = scope["one"](name)
                self.assertEqual(calls, [cut], "resume must reuse existing bytes")
                self.assertEqual(Path(staged).read_bytes(), data)
                self.assertFalse(partial.exists())
                self.assertEqual(scope["one"](name), staged)
                self.assertEqual(calls, [cut], "verified stage must not redownload")
                self.assertFalse((Path(folder) / name).exists(),
                                 "must not publish into live shard path")


if __name__ == "__main__":
    unittest.main()
