#!/usr/bin/env python3
"""Synthetic source-ZIP tests. DO NOT count as live Windows/OneHost acceptance."""
from pathlib import Path
import hashlib,json,sys,tempfile,unittest,zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from stage_genesis_web import stage,ASSET,SCHEMA,STATUS

def digest(raw):return hashlib.sha256(raw).hexdigest()

class GenesisWebStaging(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.src=self.root/"original_merged_source.zip"
        self.js=self.root/"nox_genesis_live_panel.mjs"
        self.js.write_bytes(b"/* nox-genesis-live-evidence-v1 */\n"+
                            b"/* onehost HOLD if source absent */\n"+b"const foo=1;\n"*90)
        self.files={
            "site/index.html":b"<html><body>Original cinematic D02</body></html>",
            "site/training.html":b"<html><body>Original training</body></html>",
            "site/pc/resonance.html":b"<html><body>Original Resonance</body></html>",
            "site/pc/memory.html":b"<html><body>Original S03</body></html>",
            "site/pc/chat.html":b"<html><body>Chat from PC</body></html>",
            "site/nox-orbit-original.js":b"// immutable original orbit",
        }
        self.make_source()
    def make_source(self,override=None):
        data=dict(self.files)
        receipt={"schema":"NOX-WEB-WOW-V25-PHYSICAL-SOURCE-STAGING-v1",
                 "status":"SOURCE_MERGED_PHYSICAL_ONEHOST_QA_HOLD",
                 "production_modified":False,"release_accepted":False,
                 "original_index_sha256":digest(data["site/index.html"])}
        data["NOX_PHYSICAL_MERGE_RECEIPT.json"]=json.dumps(receipt).encode()
        if override:
            data.update(override)
        with zipfile.ZipFile(self.src,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for name,content in data.items():z.writestr(name,content)
        return data
    def test_original_d02_and_every_unrelated_source_preserved(self):
        before=self.make_source()
        out=self.root/"stage"
        result=stage(self.src,self.js,out)
        self.assertEqual(result["state"],STATUS)
        with zipfile.ZipFile(out/"NOX_WEB_WOW_V25_GENESIS_S03_SOURCE_CANDIDATE.zip") as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(z.read("site/index.html"),self.files["site/index.html"])
            self.assertEqual(z.read("site/nox-orbit-original.js"),self.files["site/nox-orbit-original.js"])
            for path,original in before.items():
                if path not in ("site/training.html","site/pc/resonance.html",
                                "site/pc/memory.html","site/pc/chat.html"):
                    self.assertEqual(z.read(path),original)
            self.assertIn(b'src="../nox_genesis_live_panel.mjs"',z.read("site/pc/resonance.html"))
            self.assertIn(b'src="./nox_genesis_live_panel.mjs"',z.read("site/training.html"))
            self.assertEqual(z.read(ASSET),self.js.read_bytes())
            meta=json.loads(z.read("NOX_GENESIS_STAGING_RECEIPT.json"))
            self.assertEqual(meta["schema"],SCHEMA)
            self.assertFalse(meta["windows_e07_accepted"])
            self.assertFalse(meta["gpu_training_verified"])
            self.assertFalse(meta["release_accepted"])
    def test_prevents_no_loss_overwrite(self):
        output=self.root/"out"
        stage(self.src,self.js,output)
        with self.assertRaisesRegex(ValueError,"NOX_NO_LOSS_OUTPUT_ALREADY_EXISTS"):
            stage(self.src,self.js,output)
    def test_unverified_source_receipt_holds(self):
        self.make_source({"NOX_PHYSICAL_MERGE_RECEIPT.json":json.dumps(
            {"status":"PASS","release_accepted":True}).encode()})
        with self.assertRaisesRegex(ValueError,"NOX_UNTRUSTED"):
            stage(self.src,self.js,self.root/"hold")
        self.assertFalse((self.root/"hold").exists())
    def test_missing_memory_route_holds(self):
        del self.files["site/pc/memory.html"]
        self.make_source()
        with self.assertRaisesRegex(ValueError,"NOX_REQUIRED_WEB_SOURCE_MISSING"):
            stage(self.src,self.js,self.root/"hold")
    def test_archive_traversal_holds(self):
        self.make_source({"../escape.txt":b"secret"})
        with self.assertRaisesRegex(ValueError,"NOX_UNSAFE_ARCHIVE_PATH"):
            stage(self.src,self.js,self.root/"hold")
    def test_original_d02_sha_tamper_holds(self):
        self.make_source()
        with zipfile.ZipFile(self.src,"a") as z:
            z.writestr("site/index.html",b"FORGED")
        with self.assertRaisesRegex(ValueError,"NOX_WINDOWS_NAME_COLLISION"):
            stage(self.src,self.js,self.root/"hold")
if __name__=="__main__":unittest.main()
