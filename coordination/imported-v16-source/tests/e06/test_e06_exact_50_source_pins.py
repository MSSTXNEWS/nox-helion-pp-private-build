"""E06 source integrity regression: original 50 staged file pins must match checkout HEAD.

This verifies Git source identity only; ZIP contents, Windows compile and E07
require separate independent gates. Always fail closed on missing sources.
"""
from __future__ import annotations
import ast
import hashlib
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGER = ROOT / "coordination/e06/stage_native_stdio.py"

def git(*args):
    p = subprocess.run(["git", "-C", str(ROOT), *args], check=False,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    if p.returncode:
        raise AssertionError("E06_GIT_SOURCE_UNAVAILABLE")
    return p.stdout.decode("ascii").strip()

def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()

def checked_worktree_blob(path: str, expected: str) -> str:
    """Check actual checkout bytes too (including the binary ZIP).

    Match the existing E06 stager's pure CRLF normalization exception. Mixed
    carriage returns are not a safe normalization and must remain rejected.
    """
    source = ROOT / path
    if not source.is_file() or source.is_symlink():
        raise AssertionError("E06_PINNED_WORKTREE_SOURCE_NOT_REGULAR:" + path)
    raw = source.read_bytes()
    observed = git_blob(raw)
    if observed != expected and b"\r\n" in raw and b"\r" not in raw.replace(b"\r\n", b""):
        observed = git_blob(raw.replace(b"\r\n", b"\n"))
    return observed

class E06StagePinTests(unittest.TestCase):
    def test_all_source_pins_match_live_commit(self):
        root = ast.parse(STAGER.read_text(encoding="utf-8"))
        bindings = [node.value for node in root.body
                    if isinstance(node, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == "ADDONS"
                        for t in node.targets)]
        self.assertEqual(len(bindings), 1)
        entries = ast.literal_eval(bindings[0])
        self.assertEqual(len(entries), 50)
        paths = set()
        destinations = set()
        for path, destination, blob in entries:
            with self.subTest(path=path):
                self.assertIs(type(path), str)
                self.assertIs(type(destination), str)
                self.assertIs(type(blob), str)
                self.assertNotIn(path, paths)
                self.assertNotIn(destination, destinations)
                self.assertTrue(path and destination)
                self.assertNotIn("..", Path(path).parts)
                self.assertNotIn("..", Path(destination).parts)
                self.assertEqual(len(blob), 40)
                self.assertEqual(git("rev-parse", "HEAD:" + path), blob)
                self.assertEqual(checked_worktree_blob(path, blob), blob)
                paths.add(path)
                destinations.add(destination)
        self.assertIn("assets/NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip", paths)

if __name__ == "__main__":
    unittest.main()
