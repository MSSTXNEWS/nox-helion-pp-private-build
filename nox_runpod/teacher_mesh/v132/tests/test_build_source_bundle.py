"""Reproducible source-only archive, Windows receiver colocation and SHA tests."""
from __future__ import annotations
import json,tempfile,unittest,zipfile
from pathlib import Path
from nox_runpod.teacher_mesh.v132 import build_source_bundle as bundle
from nox_runpod.teacher_mesh.v132.onepass_release_gate import source_report

class BundleTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp=Path(temp.name)
        self.receipt=self.temp/"receipt.json"
        self.receipt.write_text(json.dumps(source_report(Path(".")),ensure_ascii=False),encoding="utf8")
        self.output=self.temp/bundle.NAME

    def test_complete_bundle_has_all_real_windows_files(self):
        report=bundle.build(Path("."),self.output,self.receipt)
        self.assertEqual(report["state"],"SOURCE_BUNDLE_SHA_CRC_VERIFIED")
        self.assertFalse(report["production_deployed"])
        self.assertTrue(report["windows_receiver_colocated"])
        with zipfile.ZipFile(self.output) as z:
            names=z.namelist()
            self.assertIn("Windows_Offsite/NOX_V70_PC_ALL_ONEPASS.ps1",names)
            self.assertIn("Windows_Offsite/windows_offsite_receiver.ps1",names)
            self.assertIn("Windows_Offsite/NOX_V70_ONEPASS_PC.cmd",names)
            self.assertIn(bundle.MANIFEST,names)
            manifest=json.loads(z.read(bundle.MANIFEST))
            self.assertFalse(manifest["original_weights_included"])
            self.assertFalse(manifest["private_records_included"])
            self.assertFalse(manifest["windows_owner_restore_verified"])
            self.assertEqual(manifest["source_count"],len(bundle.PATHS))

    def test_deterministic_bytes_on_same_source(self):
        a=bundle.build(Path("."),self.output,self.receipt)
        second=self.temp/("copy-"+bundle.NAME)
        b=bundle.build(Path("."),second,self.receipt)
        self.assertEqual(a["sha256"],b["sha256"])

    def test_refuses_preexisting_unverified_archive(self):
        self.output.write_bytes(b"do not replace")
        with self.assertRaisesRegex(ValueError,"HOLD_BUNDLE_OUTPUT_EXISTS"):
            bundle.build(Path("."),self.output,self.receipt)
        self.assertEqual(self.output.read_bytes(),b"do not replace")

    def test_refuses_false_live_completion_claim(self):
        d=json.loads(self.receipt.read_text())
        d["release"]["state"]="DONE"
        self.receipt.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,"HOLD_UNVERIFIED_OR_FALSE_RELEASE_RECEIPT"):
            bundle.build(Path("."),self.output,self.receipt)

    def test_refuses_extra_zip_member(self):
        bundle.build(Path("."),self.output,self.receipt)
        with zipfile.ZipFile(self.output,"a") as z:z.writestr("secrets.txt",b"never publish")
        with self.assertRaisesRegex(ValueError,"HOLD_BUNDLE_EXTRA_FILE"):
            bundle.verify(self.output)

if __name__=="__main__":unittest.main()
