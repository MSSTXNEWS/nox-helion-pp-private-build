#!/usr/bin/env python3
"""NOX V29 additional source archive verifier: real binary fixture, no code execution."""
import hashlib,json,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from reassemble_v29_extra_sources import verify,GROUPS
class Tests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.group="kernels"
        self.prefix=GROUPS[self.group]
        self.payload=b"NOX real source archive bytes, test only\n"*1000
        self.create()
    def create(self,mutate=False):
        fragments=[self.payload[:11500],self.payload[11500:]]
        parts=[]
        for i,data in enumerate(fragments):
            p=self.root/(self.prefix+"_PART_%02d.zip"%i)
            with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:
                z.writestr("transfer/parts/piece%02d"%i,data)
            parts.append({"name":"piece%02d"%i,"bytes":len(data),
                          "sha256":hashlib.sha256(data).hexdigest()})
        index={"schema":"nox-v29-source-chunks-v1","group":self.group,
               "archive_name":"NOX_V29_SOURCE_TREE.tar",
               "archive_bytes":len(self.payload),
               "archive_sha256":hashlib.sha256(self.payload).hexdigest(),
               "parts":parts}
        if mutate:index["archive_sha256"]="0"*64
        with zipfile.ZipFile(self.root/(self.prefix+"_INDEX.zip"),"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("transfer/PARTS_INDEX.json",json.dumps(index))
    def test_source_bytes_and_sha_verified_without_extract(self):
        r=verify(self.root,self.group)
        self.assertEqual(r["state"],"FULL_SOURCE_TAR_SHA256_VERIFIED")
        self.assertEqual(r["pieces"],2)
        self.assertFalse(r["code_executed"])
        self.assertIsNone(r["assembled_file"])
    def test_assemble_file_requires_existing_dir_and_no_overwrite(self):
        dst=self.root/"out"
        dst.mkdir()
        r=verify(self.root,self.group,out=dst)
        self.assertEqual((dst/(self.prefix+".tar")).read_bytes(),self.payload)
        self.assertEqual(r["bytes"],len(self.payload))
        with self.assertRaisesRegex(ValueError,"NOX_NO_OVERWRITE"):
            verify(self.root,self.group,out=dst)
    def test_bad_root_sha_holds(self):
        self.create(mutate=True)
        with self.assertRaisesRegex(ValueError,"NOX_FULL_ARCHIVE_SHA256_MISMATCH"):
            verify(self.root,self.group)
    def test_wrong_group_holds(self):
        with self.assertRaisesRegex(ValueError,"NOX_UNKNOWN_GROUP"):
            verify(self.root,"not_real")
    def test_missing_zip_piece_holds(self):
        (self.root/(self.prefix+"_PART_01.zip")).unlink()
        with self.assertRaises(FileNotFoundError):
            verify(self.root,self.group)
if __name__=="__main__":unittest.main()
