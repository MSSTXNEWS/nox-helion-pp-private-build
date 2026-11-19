"""Two-archive preflight proof; no NOX host mutation or real web assets."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import warnings
from zipfile import ZipFile, ZIP_DEFLATED

SOURCE=Path(__file__).with_name("merge_web_source.py")
spec=importlib.util.spec_from_file_location("nox_zip_atomic_preflight",SOURCE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ArchivePreflightTests(unittest.TestCase):
    def setup_archives(self,root,second_bad):
        v4=root/'v4.zip';v11=root/'v11.zip'
        with ZipFile(v4,'w',compression=ZIP_DEFLATED) as z:
            z.writestr('first.txt','hello')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with ZipFile(v11,'w',compression=ZIP_DEFLATED) as z:
                z.writestr('second.txt','world')
                if second_bad:z.writestr('second.txt','unexpected duplicate')
        m.V4=m.sha(v4)
        m.V11=m.sha(v11)
        return v4,v11

    def test_corrupt_second_archive_cannot_write_part_of_first(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            v4,v11=self.setup_archives(root,True)
            out=root/'output'
            with self.assertRaisesRegex(ValueError,'Duplicate zip member'):
                m.merge(v4,v11,root/'missing-overlay',out)
            self.assertFalse(out.exists())

    def test_both_valid_archives_overlay_empty_still_merge(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            v4,v11=self.setup_archives(root,False)
            overlay=root/'overlay'
            receipt=overlay/'execution/pass49/role5/source-receipt.json'
            receipt.parent.mkdir(parents=True)
            receipt.write_text('{"source_overlay":{}}')
            out=root/'output'
            m.merge(v4,v11,overlay,out)
            self.assertEqual((out/'first.txt').read_text(),'hello')
            self.assertEqual((out/'second.txt').read_text(),'world')

if __name__=='__main__':
    unittest.main()
