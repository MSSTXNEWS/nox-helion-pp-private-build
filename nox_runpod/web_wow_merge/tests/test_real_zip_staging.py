"""End-to-end source ZIP staging tests. Deliberately no live GPU/OneHost mocks."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from merge_nox_web_wow import (ROUTES, choose_chat_sources, dependencies,
                              merge, read_archive, safe_archive_name,
                              verify_onepass)

SCRIPT = Path(__file__).resolve().parents[1] / "merge_nox_web_wow.py"


def make_zip(file: Path, contents: dict[str, bytes]):
    with zipfile.ZipFile(file, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in contents.items():
            z.writestr(name, data)


def web_files():
    return {p: (b"ORIGINAL D02 14 WORLDS" if p == "index.html"
                else b"<html><body>ORIGINAL WEB</body></html>") for p in ROUTES}


def chat_v25():
    return {
        "chat.html": b'<html><script src="./chat-ui-v25.js"></script></html>',
        "memory.html": b'<html><script src="./memory-ui-v25.js"></script></html>',
        "chat-ui-v25.js": b'import "./nox-client-v25.mjs";\n',
        "nox-client-v25.mjs": b'export const noxClient = "EXISTING_ONEHOST";\n',
        "memory-ui-v25.js": b"const memory = 'S03';\n",
    }


def chat_v24():
    return {
        "chat.html": b'<html><script src="./legacy.js"></script></html>',
        "memory.html": b"V24_MEMORY_OLD",
        "legacy.js": b"OLD_UI",
        "fallback.css": b":root{color:white}",
    }


def onepass_pack():
    return {name: b"source of original ONEPASS" for name in (
        "NOX_ONEPASS.mjs", "START_NOX_ONEPASS.cmd", "NOX_LIVE_ONEHOST_E2E.mjs")}


class RealZipStaging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.web = self.root / "web.zip"
        self.v25 = self.root / "chat25.zip"
        self.v24 = self.root / "chat24.zip"
        self.qa = self.root / "qa.zip"
        make_zip(self.web, {"WEB/site/" + p: d for p, d in web_files().items()})
        make_zip(self.v25, {"EXPORTED_V25/site/" + p: d for p, d in chat_v25().items()})
        make_zip(self.v24, {"EXPORTED_V24/site/" + p: d for p, d in chat_v24().items()})
        make_zip(self.qa, {"ONEPASS/" + p: d for p, d in onepass_pack().items()})

    def run_merge(self):
        out = self.root / "staging"
        cmd = [sys.executable, str(SCRIPT), "--web-v25", str(self.web),
               "--chat-v25", str(self.v25), "--chat-v24", str(self.v24),
               "--onepass-v2", str(self.qa), "--output", str(out)]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60), out

    def test_real_zip_to_zip_preserves_web_and_adds_chat_onepass(self):
        run, out = self.run_merge()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        external = json.loads((out / "NOX_MERGE_RECEIPT.json").read_text(encoding="utf-8"))
        self.assertEqual(external["status"], "SOURCE_MERGED_PHYSICAL_QA_HOLD")
        self.assertFalse(external["owner_acceptance"])
        self.assertFalse(external["production_modified"])
        self.assertEqual(external["onepass"]["executed"], False)
        merged = out / "NOX_WEB_WOW_V25_UNIFIED_CANDIDATE.zip"
        self.assertEqual(external["output_zip_sha256"], hashlib.sha256(merged.read_bytes()).hexdigest())
        with zipfile.ZipFile(merged) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read("site/index.html"), b"ORIGINAL D02 14 WORLDS")
            self.assertEqual(z.read("site/chat.html"), chat_v25()["chat.html"])
            self.assertEqual(z.read("site/memory.html"), chat_v25()["memory.html"])
            self.assertEqual(z.read("site/nox-client-v25.mjs"),
                             chat_v25()["nox-client-v25.mjs"])
            self.assertEqual(z.read("qa/onepass_v2_original/NOX_ONEPASS.mjs"),
                             onepass_pack()["NOX_ONEPASS.mjs"])
            self.assertNotIn("qa/NOX_ONEPASS_V2_SOURCE_UNEXECUTED.zip", z.namelist())
            self.assertIn("qa/QA_NOTES.txt", z.namelist())
            self.assertNotIn("site/legacy.js", z.namelist())

    def test_missing_real_resource_holds_and_writes_receipt_no_artifact(self):
        broken = chat_v25()
        broken["chat.html"] = b'<script src="./critical-missing.mjs"></script>'
        make_zip(self.v25, {"export/" + p: d for p, d in broken.items()})
        run, out = self.run_merge()
        self.assertEqual(run.returncode, 2)
        r = json.loads((out / "NOX_MERGE_RECEIPT.json").read_text(encoding="utf-8"))
        self.assertEqual(r["status"], "HOLD_CONFLICTS")
        self.assertTrue(any(x["reason"] == "MISSING_STATIC_DEPENDENCY" for x in r["conflicts"]))
        self.assertFalse((out / "NOX_WEB_WOW_V25_UNIFIED_CANDIDATE.zip").exists())

    def test_shared_dependency_conflicts_not_overwritten(self):
        w = web_files()
        w["chat-ui-v25.js"] = b"REAL EXISTING WEB DEPENDENCY"
        make_zip(self.web, {"site/" + p: d for p, d in w.items()})
        run, out = self.run_merge()
        self.assertEqual(run.returncode, 2)
        r = json.loads((out / "NOX_MERGE_RECEIPT.json").read_text(encoding="utf-8"))
        self.assertTrue(any(x["reason"] == "SHARED_DEPENDENCY_DIFFERENT_SHA" for x in r["conflicts"]))
        self.assertFalse((out / "NOX_WEB_WOW_V25_UNIFIED_CANDIDATE.zip").exists())

    def test_archive_zip_slip_is_rejected(self):
        make_zip(self.web, {"../outside.py": b"unsafe", "site/index.html": b"x"})
        run, out = self.run_merge()
        self.assertEqual(run.returncode, 2)
        self.assertIn("NOX_UNSAFE_ARCHIVE_ENTRY", run.stderr)
        self.assertFalse(out.exists())

    def test_windows_archive_case_collisions_rejected(self):
        make_zip(self.v25, {"web/chat.html": b"chat", "web/memory.html": b"memory",
                            "web/a.js": b"x", "web/A.js": b"y"})
        run, out = self.run_merge()
        self.assertEqual(run.returncode, 2)
        self.assertIn("NOX_CASEFOLD_ZIP_COLLISION", run.stderr)
        self.assertFalse(out.exists())

    def test_no_v24_html_fallback_when_v25_page_missing(self):
        make_zip(self.v25, {"chat.html": b"chat without memory.html"})
        run, out = self.run_merge()
        self.assertEqual(run.returncode, 2)
        self.assertIn("NOX_CHAT_V25_BOTH_ENTRYPOINTS_REQUIRED", run.stderr)
        self.assertFalse(out.exists())

    def test_missing_qa_runner_holds_without_output(self):
        make_zip(self.qa, {"ONEPASS/NOX_ONEPASS.mjs": b"x"})
        run, out = self.run_merge()
        self.assertEqual(run.returncode, 2)
        self.assertIn("NOX_ONEPASS_REQUIRED_FILE_MISSING", run.stderr)
        self.assertFalse(out.exists())

    def test_refuse_to_overwrite_existing_staging(self):
        run, out = self.run_merge()
        self.assertEqual(run.returncode, 0)
        another, _ = self.run_merge()
        self.assertEqual(another.returncode, 2)
        self.assertIn("NOX_OUTPUT_ALREADY_EXISTS_NO_OVERWRITE", another.stderr)

    def test_detect_es_imports_and_urls_without_executing_code(self):
        source = (b'import "./modules/a.mjs"; fetch("./state.json"); '
                  b'const s = "no execution";')
        self.assertEqual(dependencies("js/controller.js", source),
                         {"js/modules/a.mjs", "js/state.json"})

    def test_reject_windows_device_paths(self):
        for path in ("CON.txt", "foo/PRN.js", "foo/a.js.", "foo\\b.js",
                     "foo//bar", "foo/../bar", "C:evil.js"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    safe_archive_name(path)

    def test_v24_can_fill_only_version_missing_module(self):
        v25 = chat_v25()
        v25["memory.html"] = b'<script src="./legacy-helper.js"></script>'
        v24 = chat_v24()
        v24["legacy-helper.js"] = b"actual missing dependency"
        site, r = merge(web_files(), v25, v24)
        self.assertEqual(site["legacy-helper.js"], v24["legacy-helper.js"])
        self.assertEqual(r["v24_dependency_count"], 1)
        self.assertEqual(site["memory.html"], v25["memory.html"])


if __name__ == "__main__":
    unittest.main()
