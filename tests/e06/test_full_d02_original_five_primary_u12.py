"""Narrow fail-closed source regression. No synthetic UIA/Windows PASS."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import json
import unittest
import sys

ROOT=Path(__file__).resolve().parents[2]
STAGER=ROOT/"coordination/express/publish_original_d02_primary_u12.py"
SCRIPT=ROOT/"coordination/express/stage_original_five_primary.py"
sys.path.insert(0,str(SCRIPT.parent))
spec=importlib.util.spec_from_file_location("d02_primary_u12",STAGER)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class D02OriginalFivePrimary(unittest.TestCase):
 def setUp(self):
  tmp=TemporaryDirectory(); self.addCleanup(tmp.cleanup)
  self.folder=Path(tmp.name)
  self.root=self.folder/"R11"
  (self.root/"Assets").mkdir(parents=True)
  self.home=self.root/"Assets"/"index.html"
  self.receipt=self.folder/"D02_EXISTING_FIVE_PRIMARY_RECEIPT.json"
  self.home.write_bytes(b"ORIGINAL_FIXTURE")
 def test_atomic_publish_one_home_with_unaccepted_state(self):
  derived=b'<nav>'+b''.join(('data-nox-primary="'+name+'"').encode() for name in ('CHAT','INSTALL','MODELS','LEARN','SETTINGS'))+b'</nav>'
  proof={'source_sha256':hashlib.sha256(self.home.read_bytes()).hexdigest(),
         'published_sha256':hashlib.sha256(derived).hexdigest(),
         'installed_ui_automation':'NOT_RUN','release_accepted':False}
  with patch.object(module,'publish',return_value=(derived,proof)):
   got=module.stage(self.root,self.receipt)
  self.assertEqual(self.home.read_bytes(),derived)
  self.assertEqual(json.loads(self.receipt.read_text('utf-8')),got)
  self.assertEqual(got['independent_e07'],'HOLD')
  self.assertFalse(got['release_accepted'])
 def test_real_unreviewed_bytes_fail_closed_no_home_mutation(self):
  before=self.home.read_bytes()
  with self.assertRaisesRegex(ValueError,'U08_ORIGINAL_HOME_BYTES_HOLD'):
   module.stage(self.root,self.receipt)
  self.assertEqual(before,self.home.read_bytes())
  self.assertFalse(self.receipt.exists())
 def test_existing_receipt_rejected_without_overwrite(self):
  self.receipt.write_text('already owned')
  with self.assertRaisesRegex(ValueError,'D02_PRIMARY_DISPOSABLE_PATH_HOLD'):
   module.stage(self.root,self.receipt)
  self.assertEqual(self.receipt.read_text(),'already owned')
 def test_foreign_pending_racing_exclusive_open_is_preserved(self):
  derived=b"<nav>"+b"".join(("data-nox-primary=\\\""+s+"\\\"").encode() for s in ("CHAT","INSTALL","MODELS","LEARN","SETTINGS"))+b"</nav>"
  proof={"source_sha256":hashlib.sha256(self.home.read_bytes()).hexdigest(),
         "published_sha256":hashlib.sha256(derived).hexdigest(),
         "installed_ui_automation":"NOT_RUN","release_accepted":False}
  pending=self.home.with_name("index.html.nox-u12-pending")
  from pathlib import Path as _Path
  real_open=_Path.open
  before=self.home.read_bytes()
  def competing_open(path,mode="r",*args,**kwargs):
   if path==pending and mode=="xb":
    with real_open(pending,"wb") as f: f.write(b"FOREIGN_UNMANAGED_BYTES")
    raise FileExistsError("competing writer created the pending file")
   return real_open(path,mode,*args,**kwargs)
  with patch.object(module,"publish",return_value=(derived,proof)), patch.object(_Path,"open",competing_open):
   with self.assertRaises(FileExistsError):module.stage(self.root,self.receipt)
  self.assertEqual(pending.read_bytes(),b"FOREIGN_UNMANAGED_BYTES")
  self.assertEqual(self.home.read_bytes(),before)
  self.assertFalse(self.receipt.exists())
 def test_foreign_receipt_race_never_replaces_home(self):
  derived=b'<nav>'+b''.join(('data-nox-primary="'+name+'"').encode() for name in ('CHAT','INSTALL','MODELS','LEARN','SETTINGS'))+b'</nav>'
  proof={'source_sha256':hashlib.sha256(self.home.read_bytes()).hexdigest(),
         'published_sha256':hashlib.sha256(derived).hexdigest(),
         'installed_ui_automation':'NOT_RUN','release_accepted':False}
  before=self.home.read_bytes()
  from pathlib import Path as _Path
  real_open=_Path.open
  def competing_receipt(path,mode="r",*args,**kwargs):
   if path==self.receipt and mode=="x":
    with real_open(self.receipt,"w",encoding="utf-8") as foreign:
     foreign.write("FOREIGN_RECEIPT_MUST_SURVIVE")
    raise FileExistsError("competing receipt owner won")
   return real_open(path,mode,*args,**kwargs)
  with patch.object(module,'publish',return_value=(derived,proof)), patch.object(_Path,'open',competing_receipt):
   with self.assertRaises(FileExistsError): module.stage(self.root,self.receipt)
  self.assertEqual(self.home.read_bytes(),before)
  self.assertEqual(self.receipt.read_text('utf-8'),"FOREIGN_RECEIPT_MUST_SURVIVE")
  self.assertFalse(self.home.with_name("index.html.nox-u12-pending").exists())
 def test_reparse_home_rejected(self):
  self.home.unlink()
  other=self.folder/'unmanaged';other.write_text('unmanaged')
  self.home.symlink_to(other)
  with self.assertRaisesRegex(ValueError,'D02_PRIMARY_DISPOSABLE_PATH_HOLD'):
   module.stage(self.root,self.receipt)
  self.assertEqual(other.read_text(),'unmanaged')

if __name__=='__main__':unittest.main()
