"""E06 source-only tests: the existing 28-part R11 extractor reuses the sole
canonical 3-part ZIP namespace gate, without changing original source archives.
"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("nox_e06_stage_p01", ROOT/"coordination/e06/stage_p01.py")
STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE)
NEEDED = [
 "R11/MainWindow.xaml", "R11/MainWindow.xaml.cs", "R11/App.xaml",
 "R11/NOX.P01.Shell.csproj",
 "R11/Assets/index.html", "R11/Installer/NOX-HELION-Setup.nsi",
 "R11/Contracts/EventV3Bridge.cs", "R11/Packages/P04/train_qlora.py"
]

def blob(raw):
 return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

class ReusedCanonicalZipGate(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.work=self.root/"staged"
  self.receipt=self.root/"P01_C07_RECEIPT.json"
  self.patches=[
   patch.object(STAGE,"ROOT",self.root),
   patch.object(STAGE,"RECEIPT",self.receipt),
   patch.object(STAGE,"WORK",self.work),
   patch.object(STAGE,"R11",self.work/"R11")
  ]
  for p in self.patches:
   p.start();self.addCleanup(p.stop)

 def create(self, members):
  archive=io.BytesIO()
  with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED) as z:
   for name,typ in members:
    entry=zipfile.ZipInfo(name)
    entry.create_system=3
    if typ is not None:entry.external_attr=(typ|0o600)<<16
    z.writestr(entry,b"" if name.endswith("/") else b"fixture")
  data=archive.getvalue()
  sizes=[len(data)*i//28 for i in range(29)]
  records=[]
  for i in range(28):
   chunk=data[sizes[i]:sizes[i+1]]
   rel=f"parts/{i:02}.part"
   path=self.root/rel
   path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(chunk)
   records.append({"path":rel,"size_bytes":len(chunk),"git_blob_sha1":blob(chunk)})
  self.receipt.write_text(json.dumps({"parts":records,
   "original_zip_bytes":len(data),"original_zip_sha256":hashlib.sha256(data).hexdigest()}))
  return data

 def test_valid_original_layout(self):
  names=NEEDED+[f"R11/QA/extra-{i:03}.txt" for i in range(75-len(NEEDED))]
  self.create([(name,stat.S_IFREG) for name in names])
  STAGE.main()
  receipt=json.loads((self.work/"source_lock.json").read_text())
  self.assertEqual(receipt["original_members"],75)
  self.assertEqual(len(receipt["artifacts"]),75)
  self.assertFalse(receipt["release_accepted"])
  self.assertEqual((self.work/"R11/Assets/index.html").read_bytes(),b"fixture")

 def test_incomplete_wpf_donor_fails_before_creating_r11_tree(self):
  # A codebehind-only donor is not a source-complete WPF shell.
  missing=[x for x in NEEDED if x!="R11/MainWindow.xaml"]
  names=missing+[f"R11/QA/extra-{i:03}.txt" for i in range(75-len(missing))]
  self.create([(name,stat.S_IFREG) for name in names])
  with self.assertRaisesRegex(SystemExit,"P01_REQUIRED_ASSETS_MISSING"):
   STAGE.main()
  self.assertFalse((self.work/"R11").exists())
  self.assertFalse((self.work/"source_lock.json").exists())

 def test_file_parent_conflict_before_writes(self):
  self.create([("R11/Assets/index.html",stat.S_IFREG),
               ("R11/Assets",stat.S_IFREG)])
  with self.assertRaisesRegex(SystemExit,"E06_CANONICAL_ZIP_NAMESPACE_HOLD"):
   STAGE.main()
  self.assertFalse((self.work/"R11").exists())

 def test_special_unix_node_before_writes(self):
  self.create([("R11/fifo",stat.S_IFIFO)])
  with self.assertRaisesRegex(SystemExit,"E06_CANONICAL_ZIP_NAMESPACE_HOLD"):
   STAGE.main()
  self.assertFalse((self.work/"R11").exists())

 def test_existing_source_lock_is_preserved(self):
  self.create([(name,stat.S_IFREG) for name in NEEDED])
  self.work.mkdir(parents=True,exist_ok=True)
  old=b"ORIGINAL_OWNER_SOURCE_LOCK"
  (self.work/"source_lock.json").write_bytes(old)
  with self.assertRaisesRegex(SystemExit,"E06_SOURCELOCK_ALREADY_EXISTS_NO_OVERWRITE"):
   STAGE.main()
  self.assertEqual((self.work/"source_lock.json").read_bytes(),old)
  self.assertFalse((self.work/"R11").exists())

 def test_symlink_stage_ancestor_denied_before_writes(self):
  # A parent symlink escapes staging while WORK.is_symlink() remains False.
  names=NEEDED+[f"R11/QA/extra-{i:03}.txt" for i in range(75-len(NEEDED))]
  self.create([(name,stat.S_IFREG) for name in names])
  outside=self.root/"outside";outside.mkdir()
  shortcut=self.root/"link"
  try:shortcut.symlink_to(outside,target_is_directory=True)
  except (NotImplementedError,OSError) as e:self.skipTest(str(e))
  work=shortcut/"nested"/"staged"
  with patch.object(STAGE,"WORK",work), patch.object(STAGE,"R11",work/"R11"):
   with self.assertRaisesRegex(SystemExit,"E06_STAGE_REPARSE_ROOT_HOLD"):
    STAGE.main()
  self.assertEqual(list(outside.iterdir()),[])

 def test_symlink_stage_root_denied(self):
  self.create([(name,stat.S_IFREG) for name in NEEDED])
  real=self.root/"outside";real.mkdir()
  try:(self.root/"staged").symlink_to(real,target_is_directory=True)
  except (NotImplementedError,OSError) as e:self.skipTest(str(e))
  with self.assertRaisesRegex(SystemExit,"E06_STAGE_REPARSE_ROOT_HOLD"):
   STAGE.main()
  self.assertEqual(list(real.iterdir()),[])

if __name__=="__main__":
 unittest.main()
