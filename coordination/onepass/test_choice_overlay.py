"""Test ZIP overlay with a synthetic 13-select site, never mutate frozen source."""
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile
from coordination.onepass import build_choice_overlay as patcher


class OnepassChoiceOverlayTests(unittest.TestCase):
    def test_frozen_source_preserved_and_13_inputs_rebound(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            original=base/"original.zip"
            script=Path("coordination/onepass/nox_choice_buttons_v293.js")
            with zipfile.ZipFile(original,"w") as z:
                for file,n in patcher.ORIGINAL_SELECTS.items():
                    html="<html><body>" + "".join(
                        "<select class='nx-in'><option value='1'>Живой выбор</option></select>"
                        for _ in range(n)) + "</body></html>"
                    z.writestr(file,html)
                z.writestr("site/untouched.txt","do not mutate")
            sha=hashlib.sha256(original.read_bytes()).hexdigest()
            output=base/"derived.zip"
            with patch.object(patcher,"ZIP_SHA256",sha),patch.object(patcher,"ZIP_FILES",6):
                result=patcher.build(original,output,script)
            self.assertEqual(result["visible_dropdowns_replaced_by_live_buttons"],13)
            self.assertFalse(result["original_source_modified"])
            with zipfile.ZipFile(original) as a,zipfile.ZipFile(output) as b:
                self.assertEqual(b.testzip(),None)
                self.assertEqual(b.read("site/untouched.txt"),a.read("site/untouched.txt"))
                self.assertIn(patcher.SCRIPT_REF.encode(),b.read("site/pc/pages/games/index.html"))
                self.assertEqual(b.read(patcher.NEW_SCRIPT),script.read_bytes())
                self.assertEqual(len(b.namelist()),7)
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),sha)
    def test_wrong_source_sha_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            original=base/"wrong.zip"
            original.write_bytes(b"not trusted frozen source")
            out=base/"out.zip"
            with self.assertRaisesRegex(ValueError,"HOLD_FROZEN_ORIGINAL_SHA"):
                patcher.build(original,out,Path("coordination/onepass/nox_choice_buttons_v293.js"))
            self.assertFalse(out.exists())


if __name__=="__main__":
    unittest.main()
