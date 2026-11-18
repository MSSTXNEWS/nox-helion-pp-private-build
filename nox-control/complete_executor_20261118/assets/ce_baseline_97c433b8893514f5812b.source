"""0V14-14: an overlay manifest may only replace files inside the output root."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import merge_web_source as merger


class OverlayBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.overlay=self.root/'input/source'
        self.overlay.mkdir(parents=True)
        self.out=self.root/'output/merged'
        self.out.parent.mkdir()
        self.manifest=self.overlay/'execution/pass49/role5/source-receipt.json'
        self.manifest.parent.mkdir(parents=True)
        self.v4=self.root/'v4.zip';self.v11=self.root/'v11.zip'
        with ZipFile(self.v4,'w') as archive:
            archive.writestr('site/app.js','base')
            archive.writestr('site/preserved.txt','original')
        with ZipFile(self.v11,'w') as archive:
            archive.writestr('site/addon.js','addon')
        self.pins=patch.multiple(merger,V4=merger.sha(self.v4),V11=merger.sha(self.v11))
        self.pins.start();self.addCleanup(self.pins.stop)

    def prepare(self,name,content=b'approved overlay'):
        source=self.overlay/name
        source.parent.mkdir(parents=True,exist_ok=True)
        source.write_bytes(content)
        self.manifest.write_text(json.dumps({'source_overlay':{name:hashlib.sha256(content).hexdigest()}}))

    def run_merge(self):
        return merger.merge(self.v4,self.v11,self.overlay,self.out)

    def test_relative_traversal_cannot_overwrite_foreign_output_sibling(self):
        foreign=self.out.parent/'foreign.txt';foreign.write_bytes(b'owner original')
        self.prepare('../foreign.txt',b'other source')
        with self.assertRaisesRegex(ValueError,'Unsafe overlay path'):
            self.run_merge()
        self.assertEqual(foreign.read_bytes(),b'owner original')

    def test_absolute_overlay_key_rejected_before_copy(self):
        absolute=self.root/'absolute.txt';absolute.write_bytes(b'original')
        self.manifest.write_text(json.dumps({'source_overlay':{str(absolute):merger.sha(absolute)}}))
        with self.assertRaisesRegex(ValueError,'Unsafe overlay path'):
            self.run_merge()
        self.assertEqual(absolute.read_bytes(),b'original')

    def test_backslash_alias_is_not_a_portable_overlay_path(self):
        self.prepare('site\\payload.js')
        with self.assertRaisesRegex(ValueError,'Unsafe overlay path'):
            self.run_merge()

    def test_dot_alias_does_not_bypass_unique_manifest_paths(self):
        self.prepare('site/./app.js')
        with self.assertRaisesRegex(ValueError,'Unsafe overlay path'):
            self.run_merge()

    def test_overlay_source_symlink_cannot_import_foreign_file(self):
        outside=self.root/'foreign-source';outside.write_bytes(b'foreign')
        source=self.overlay/'site/app.js';source.parent.mkdir(parents=True)
        source.symlink_to(outside)
        self.manifest.write_text(json.dumps({'source_overlay':{'site/app.js':merger.sha(outside)}}))
        with self.assertRaisesRegex(ValueError,'Unsafe overlay source'):
            self.run_merge()
        self.assertEqual(outside.read_bytes(),b'foreign')

    def test_valid_overlay_preserves_union_and_changes_only_named_file(self):
        self.prepare('site/app.js')
        self.assertEqual(self.run_merge(),self.out)
        self.assertEqual((self.out/'site/app.js').read_bytes(),b'approved overlay')
        self.assertEqual((self.out/'site/preserved.txt').read_text(),'original')
        self.assertEqual((self.out/'site/addon.js').read_text(),'addon')


if __name__=='__main__':unittest.main()
