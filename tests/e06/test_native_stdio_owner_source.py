"""Contract for pinned existing source-only OriginalPython→NativeIngress adapter."""
from pathlib import Path
import ast
import unittest
ROOT=Path(__file__).resolve().parents[2]
class NativeOwnerSourceTest(unittest.TestCase):
    def test_existing_original_backend_not_second_host(self):
        stage=(ROOT/"coordination/e06/stage_native_stdio.py").read_text("utf-8")
        owner=(ROOT/"coordination/e06/e06_native_stdio_owner.py").read_text("utf-8")
        ast.parse(stage);ast.parse(owner)
        self.assertIn("ORIGINAL_APP_SHA256",stage)
        self.assertIn("native_stdio_requires_exclusive_trusted_run_id",stage)
        self.assertIn("E06_NATIVE_OWNER_BLOB_SHA_HOLD",stage)
        self.assertIn("serve_native_frames(ingress, sys.stdin.buffer, sys.stdout.buffer)",owner)
        self.assertIn("NativeIngress(dispatcher",owner)
        self.assertIn("NativeSession(",owner)
        self.assertIn('allowed=frozenset({"chat.model"})',owner)
        self.assertNotIn("HttpServer",owner)
        self.assertNotIn("sqlite3.connect(",owner)
