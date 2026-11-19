import sys
import json
import tempfile
import zipfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from merge_physical_web_v25 import merge_physical, clean_static, local_entry, output
from merge_nox_web_wow import ROUTES


def original_web():
    return {name: (b"ORIGINAL D02 14 WORLDS" if name == "index.html" else
                   b"<html><body>WEB</body></html>") for name in ROUTES}


def chat():
    return {
        "chat.html": b'<meta http-equiv="refresh" content="0;url=resonance.html">',
        "index.html": b'<a href="/world.html">World</a>',
        "memory.html": b'<html>REAL S03 <script src="./memory.js"></script></html>',
        "resonance.html": b'<html>REAL NOX RESONANCE <script src="./resonance.js"></script></html>',
        "resonance.js": b'const existing = "/api/nox/chat";',
        "memory.js": b'const existing = "/api/nox/memory";',
        "world.html": b'<a href="/menu.html">Menu</a>',
        "menu.html": b'<a href="/hub.html">Hub</a>',
        "hub.html": b'<a href="/world.html">World</a>',
        "vendor/fonts/tektur/tektur.css": b"body{font-family:Tektur}",
    }


class PhysicalMergerTests(unittest.TestCase):
    def test_original_d02_and_all_original_pages_preserved(self):
        w=original_web()
        site,qa,receipt=merge_physical(w,chat(),{},{"NOX_ONEPASS.mjs":b"script"})
        self.assertEqual(site["index.html"],w["index.html"])
        for page in ROUTES:
            if page not in ("chat.html","memory.html"):
                self.assertEqual(site[page],w[page])
        self.assertEqual(site["original_web_v25_1/chat.html"],w["chat.html"])
        self.assertEqual(site["original_web_v25_1/memory.html"],w["memory.html"])
        self.assertEqual(receipt["status"],"SOURCE_MERGED_PHYSICAL_ONEHOST_QA_HOLD")
        self.assertFalse(receipt["release_accepted"])
        self.assertFalse(receipt["production_modified"])

    def test_pc_resonance_memory_and_navigation_really_wired(self):
        site,qa,r=merge_physical(original_web(),chat(),{},{"NOX_ONEPASS.mjs":b"script"})
        self.assertIn(b"pc/resonance.html",site["chat.html"])
        self.assertIn(b"pc/memory.html",site["memory.html"])
        self.assertIn(b"/pc/world.html",site["pc/index.html"])
        self.assertIn(b"/pc/menu.html",site["pc/world.html"])
        self.assertIn(b"/pc/hub.html",site["pc/menu.html"])
        self.assertIn(b"/api/nox/chat",site["pc/resonance.js"])
        self.assertIn(b"/api/nox/memory",site["pc/memory.js"])

    def test_v24_only_missing_never_replaces_v25(self):
        new=chat()
        old={"resonance.html":b"stale wrong chat",
             "missing-v24.js":b"old library"}
        site,qa,receipt=merge_physical(original_web(),new,old,{"NOX_ONEPASS.mjs":b"x"})
        self.assertEqual(site["pc/resonance.html"],new["resonance.html"])
        self.assertEqual(site["pc/missing-v24.js"],b"old library")
        self.assertEqual(receipt["pc_v24_fallback_files"],1)

    def test_explicit_third_party_firebase_key_removed(self):
        name="pages/_vendor/excalidraw/excalidraw.production.min.js"
        secret=b"AIza"+b"x"*35
        src=b'VITE_APP_FIREBASE_CONFIG:{"apiKey":"'+secret+b'"}'
        out=clean_static(name,src)
        self.assertNotIn(secret,out)
        self.assertIn(b'"apiKey":""',out)

    def test_unknown_source_tokens_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"POTENTIAL_SECRET_HOLD"):
            clean_static("resonance.js",b"const x='github_pat_" +b"x"*30+b"'")

    def test_build_zip_contains_no_duplicate_backend_and_original_qa(self):
        site,qa,receipt=merge_physical(original_web(),chat(),{},
                                       {"NOX_ONEPASS.mjs":b"QA SOURCE"})
        with tempfile.TemporaryDirectory() as d:
            dst=Path(d)/"out"
            src=Path(d)/"source.zip"
            src.write_bytes(b"fixture")
            built=output(dst,site,qa,receipt,{"synthetic":src})
            self.assertEqual(built.stat().st_size,receipt["output_zip_bytes"])
            with zipfile.ZipFile(built) as z:
                self.assertIsNone(z.testzip())
                self.assertEqual(z.read("site/index.html"),b"ORIGINAL D02 14 WORLDS")
                self.assertIn("qa/onepass_v2_original/NOX_ONEPASS.mjs",z.namelist())
                self.assertNotIn("app/nox_chat_server.py",z.namelist())
                self.assertFalse(json.loads(z.read("NOX_PHYSICAL_MERGE_RECEIPT.json"))["release_accepted"])

if __name__=="__main__":
    unittest.main()
