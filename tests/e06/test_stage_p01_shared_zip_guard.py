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

 def test_verified_original_p01_wpf_donor_receipt(self):
  # Check real native WPF donor bytes; archive 729 is a separate provenance.
  owner=json.loads((ROOT/"donors/P01_C07/P01_C07_RECEIPT.json").read_text("utf-8"))
  self.assertEqual(len(owner["parts"]),28)
  joined=io.BytesIO()
  for part in owner["parts"]:
   path=ROOT/part["path"]
   self.assertTrue(path.is_file() and not path.is_symlink())
   raw=path.read_bytes()
   self.assertEqual(len(raw),part["size_bytes"])
   self.assertEqual(blob(raw),part["git_blob_sha1"])
   joined.write(raw)
  self.assertEqual(joined.tell(),owner["original_zip_bytes"])
  self.assertEqual(hashlib.sha256(joined.getvalue()).hexdigest(),owner["original_zip_sha256"])
  with zipfile.ZipFile(joined) as archive:
   self.assertIsNone(archive.testzip())
   self.assertTrue({"R11/App.xaml","R11/MainWindow.xaml",
     "R11/MainWindow.xaml.cs","R11/NOX.P01.Shell.csproj"}.issubset(archive.namelist()))
   import xml.etree.ElementTree as ET
   app=ET.fromstring(archive.read("R11/App.xaml"))
   window=ET.fromstring(archive.read("R11/MainWindow.xaml"))
   x="{http://schemas.microsoft.com/winfx/2006/xaml}Class"
   self.assertEqual(app.attrib[x],"NoxP01.App")
   self.assertEqual(app.attrib["StartupUri"],"MainWindow.xaml")
   self.assertEqual(window.attrib[x],"NoxP01.MainWindow")
   proj=ET.fromstring(archive.read("R11/NOX.P01.Shell.csproj"))
   self.assertIn("net8.0-windows",[e.text for e in proj.iter()])
   historic=json.loads(archive.read("R11/SOURCE_MANIFEST_SHA256.json"))
   receipts=json.loads(archive.read("P01_TURBO10_PATCH_RECEIPTS.json"))
   accepted={}
   self.assertEqual(len(receipts["patches"]),2)
   for p in receipts["patches"]:
    self.assertNotIn(p["path"],accepted)
    self.assertEqual(hashlib.sha256(archive.read(p["patchName"])).hexdigest(),p["patchSHA256"])
    self.assertEqual(hashlib.sha256(archive.read("R11/"+p["path"])).hexdigest(),p["postSHA256"])
    accepted[p["path"]]=p["postSHA256"]
   self.assertEqual(len(historic),79)
   for path,original in historic.items():
    self.assertEqual(hashlib.sha256(archive.read("R11/"+path)).hexdigest(),
                     accepted.get(path,original))

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

 def test_symlink_stage_root_denied(self):
  self.create([(name,stat.S_IFREG) for name in NEEDED])
  real=self.root/"outside";real.mkdir()
  try:(self.root/"staged").symlink_to(real,target_is_directory=True)
  except (NotImplementedError,OSError) as e:self.skipTest(str(e))
  with self.assertRaisesRegex(SystemExit,"E06_STAGE_REPARSE_ROOT_HOLD"):
   STAGE.main()
  self.assertEqual(list(real.iterdir()),[])

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



 def test_donor_part_traversal_fails_closed(self):
  self.create([(name,stat.S_IFREG) for name in NEEDED])
  owner=json.loads(self.receipt.read_text())
  owner["parts"][0]["path"]="../outside/private.part"
  self.receipt.write_text(json.dumps(owner))
  with self.assertRaisesRegex(SystemExit,"E06_DONOR_PATH_HOLD"):
   STAGE.main()
  self.assertFalse((self.work/"R11").exists())

 def test_donor_part_symlink_parent_fails_closed(self):
  self.create([(name,stat.S_IFREG) for name in NEEDED])
  linked=self.root/"donorlink"
  try:linked.symlink_to(self.root/"parts",target_is_directory=True)
  except (NotImplementedError,OSError) as exc:self.skipTest(str(exc))
  owner=json.loads(self.receipt.read_text())
  owner["parts"][0]["path"]="donorlink/00.part"
  self.receipt.write_text(json.dumps(owner))
  with self.assertRaisesRegex(SystemExit,"E06_DONOR_PATH_HOLD"):
   STAGE.main()
  self.assertFalse((self.work/"R11").exists())

 def test_existing_r11_keeps_original_data(self):
  self.create([(name,stat.S_IFREG) for name in NEEDED])
  r11=self.work/"R11";r11.mkdir(parents=True)
  marker=r11/"USER_DATA.txt";marker.write_bytes(b"ORIGINAL_USER_DATA")
  with self.assertRaisesRegex(SystemExit,"E06_R11_ALREADY_EXISTS_NO_OVERWRITE"):
   STAGE.main()
  self.assertEqual(marker.read_bytes(),b"ORIGINAL_USER_DATA")
  self.assertEqual([p.name for p in r11.iterdir()],["USER_DATA.txt"])
  self.assertFalse((self.work/"source_lock.json").exists())

if __name__=="__main__":
 unittest.main()
