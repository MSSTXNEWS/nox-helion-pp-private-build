"""Independent SOURCE QA: WOW200 exact source pin parity.

This intentionally fails on current PR162 because stage_wow200.py pins an older
approved D02 JS blob than the actual owner #1 JS. It does not run the installer,
change any source bytes, or declare a Windows E2E result.

Run: python -m unittest discover -s qa/source_ready -p 'test_wow200_d02_owner_pin_r04.py' -v
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAGER = ROOT / "integrations/wow200/stage_wow200.py"
LEGACY = ROOT / "integrations/wow200"
MJS = "proposals/NOX-CINEMA-FX/nox-cinema.mjs"
CSS = "proposals/NOX-CINEMA-FX/nox-cinema.css"


def git_blob_sha(path: Path) -> str:
    if not path.is_file() or path.is_symlink():
        raise AssertionError("MISSING_OR_SYMLINK_SOURCE:" + str(path))
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def approved_pins():
    source = STAGER.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(STAGER))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "OWNER1_D02_ENGINE"
                for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("OWNER1_D02_ENGINE_PIN_MAP_MISSING")


class ApprovedD02SourcePins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pins = approved_pins()

    def test_owner_js_actual_blob_matches_stager_pin(self):
        # RED before owner #1 updates pins with a matching, reviewed test.
        self.assertEqual(git_blob_sha(ROOT / MJS),
                         self.pins[MJS]["active_blob"],
                         "OWNER1_D02_ENGINE_SHA_HOLD: actual JS changed without stage pin")

    def test_owner_css_actual_blob_matches_stager_pin(self):
        self.assertEqual(git_blob_sha(ROOT / CSS), self.pins[CSS]["active_blob"])

    def test_legacy_js_is_preserved_and_pinned(self):
        self.assertEqual(git_blob_sha(LEGACY / MJS), self.pins[MJS]["legacy_blob"])

    def test_legacy_css_is_preserved_and_pinned(self):
        self.assertEqual(git_blob_sha(LEGACY / CSS), self.pins[CSS]["legacy_blob"])

    def test_runtime_home_imports_only_staged_active_owner(self):
        source = (LEGACY / "runtime/home-scene.mjs").read_text(encoding="utf-8")
        self.assertIn("from '../proposals/NOX-CINEMA-FX/nox-cinema.mjs'", source)

    def test_fail_closed_stager_never_skips_active_pin(self):
        source = STAGER.read_text(encoding="utf-8")
        self.assertIn('gitsha(active.read_bytes())!=pins["active_blob"]', source)
        self.assertIn("OWNER1_D02_ENGINE_SHA_HOLD", source)
        self.assertIn('plans.append((owner1_root/rel,dest/rel))', source)


if __name__ == "__main__":
    unittest.main()
