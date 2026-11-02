"""Original approved MEGA814 source admission: byte provenance and -O fail-closed."""
import pathlib, subprocess, sys, tempfile, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from stage_original_r11 import NAMES, SOURCE, OWNER_BLOB_PINS, approved_source, git_blob_sha

class OwnerSourceAdmission(unittest.TestCase):
 def test_all_eight_approved_donor_preimages(self):
  self.assertEqual(set(NAMES),set(OWNER_BLOB_PINS))
  for name in NAMES:
   with self.subTest(source=name):
    path=SOURCE/name
    raw=approved_source(path,name)
    self.assertEqual(git_blob_sha(raw),OWNER_BLOB_PINS[name])
 def test_active_native_js_tampering_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   file=pathlib.Path(folder)/"native-readonly.mjs"
   file.write_bytes(b'window.chrome.webview.postMessage({action:"fake-grant"});')
   with self.assertRaisesRegex(RuntimeError,"MEGA814_APPROVED_SOURCE_BLOB_HOLD"):
    approved_source(file,"native-readonly.mjs")
 def test_manifest_tampering_rejected_before_parse(self):
  with tempfile.TemporaryDirectory() as folder:
   file=pathlib.Path(folder)/"manifest.json"
   file.write_bytes(b'{"schema":"NOX-MEGA814-V16-OWNER-SOURCE-v1","release":"PASS"}')
   with self.assertRaisesRegex(RuntimeError,"MEGA814_APPROVED_SOURCE_BLOB_HOLD"):
    approved_source(file,"manifest.json")
 def test_missing_unapproved_source_fails_closed(self):
  with tempfile.TemporaryDirectory() as folder:
   path=pathlib.Path(folder)/"missing.js"
   with self.assertRaisesRegex(RuntimeError,"MEGA814_APPROVED_SOURCE_PATH_HOLD"):
    approved_source(path,"missing.js")
 def test_optimized_python_cannot_skip_original_qa(self):
  gate=pathlib.Path(__file__).resolve().parent/"qa_source_gate.py"
  result=subprocess.run([sys.executable,"-O",str(gate)],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        text=True,timeout=20,check=False)
  self.assertNotEqual(result.returncode,0)
  self.assertIn("MEGA814_OPTIMIZED_ASSERTIONS_HOLD",result.stderr)
if __name__=="__main__":unittest.main()
