"""Single G6-A ZIP fail-closed targeted Python regression. No EXE/NSIS."""
import hashlib
import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

SCRIPT=Path(__file__).resolve().parents[5]/"coordination/e06/source_deep_inventory.py"

def load():
    spec=importlib.util.spec_from_file_location("inventory_g6a",SCRIPT)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

class G6AArchiveNamespaceTest(unittest.TestCase):
    def test_file_parent_collision_rejected_before_any_publication(self):
        m=load()
        data=io.BytesIO()
        with zipfile.ZipFile(data,"w") as z:
            z.writestr("item",b"parent")
            z.writestr("item/child",b"child")
        raw=data.getvalue()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            n=len(raw)
            for p,b in zip(m.PARTS,(raw[:n//3],raw[n//3:2*n//3],raw[2*n//3:])):
                (root/p).write_bytes(b)
            class CanonicalRejector:
                def validate_members(self,infos):
                    if [x.filename for x in infos]!=["item","item/child"]:
                        raise AssertionError("UNEXPECTED_NAMES")
                    raise ValueError("File used as parent path")
                def publish_manifest_exclusive(self,*args):
                    raise AssertionError("PUBLISH_ON_INVALID_ARCHIVE")
            with (mock.patch.object(m,"ROOT",root),
                  mock.patch.object(m,"EXPECTED_SHA",hashlib.sha256(raw).hexdigest()),
                  mock.patch.object(m,"EXPECTED_SIZE",len(raw)),
                  mock.patch.object(m,"_canonical_validator",return_value=CanonicalRejector()),
                  mock.patch.object(tempfile,"tempdir",str(root))):
                with self.assertRaisesRegex(RuntimeError,"ORIGINAL_ZIP_NAMESPACE_HOLD"):
                    m.main()
            self.assertFalse((root/"e06-source-inventory.json").exists())
            self.assertFalse((root/"e06-source-verified.zip").exists())
            self.assertFalse(list(root.glob("nox-deep-inventory-*")))

if __name__=="__main__":
    unittest.main()
