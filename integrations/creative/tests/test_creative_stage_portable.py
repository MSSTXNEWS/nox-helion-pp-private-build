"""Portable fail-closed tests; safe for Linux and Windows CI; real R13 SHA tested separately."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import stage_creative as source

class StagingSafety(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();d=Path(self.tmp.name)
        self.root=d/'R11';self.web=d/'creative'/'web';self.asset=self.root/'Assets'
        self.asset.mkdir(parents=True);self.web.mkdir(parents=True)
        (self.root/'Integration').mkdir()
        (self.root/'NOX.P01.Shell.csproj').write_text('<Project/>')
        self.main=self.root/'MainWindow.xaml.cs'
        self.main.write_text('NATIVE PRE\n'+source.ANCHOR+'\n'+source.LIFECYCLE+'\nAFTER')
        self.html=self.asset/'index.html';self.html.write_text('<html><head></head><body><main></main></body></html>')
        (self.web.parent/'bridge').mkdir()
        (self.web.parent/'bridge/CreativeHostBridge.cs').write_text('// approved owner scoped')
        for n in ['entry.js','studio.js','studio.html','studio.css','theater.html','theater.js','manifest.webmanifest']:
            (self.web/n).write_text('// '+n)
        self.original_sha={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.main,self.html)}
        self.original_d02=dict(source.D02)
        for n in source.D02:
            blob=('fixture D02 '+n).encode();(self.asset/n).write_bytes(blob)
            source.D02[n]=hashlib.sha256(blob).hexdigest()
    def tearDown(self):
        source.D02.clear();source.D02.update(self.original_d02);self.tmp.cleanup()
    def unchanged(self):
        for p,h in self.original_sha.items():self.assertEqual(hashlib.sha256(Path(p).read_bytes()).hexdigest(),h)
        self.assertFalse((self.root/'Assets/creative').exists())
        self.assertFalse((self.root/'Integration/CreativeHostBridge.cs').exists())
    def test_exact_router_additive_no_art_modification(self):
        before={n:source.sha(self.asset/n) for n in source.D02}
        receipt=source.stage(self.root,self.web.parent)
        self.assertEqual(receipt['schema'],'NOX_R13_CREATIVE_STAGE_V2_FAILCLOSED')
        self.assertIn('creativeInvoke',self.main.read_text())
        self.assertEqual({n:source.sha(self.asset/n) for n in source.D02},before)
        self.assertFalse(receipt['release_accepted'])
    def test_legacy_exact_owner_route_without_packinvoke(self):
        self.main.write_text('NATIVE PRE\\n'+source.LEGACY_ANCHOR+'\\n'+source.LIFECYCLE+'\\nAFTER')
        receipt=source.stage(self.root,self.web.parent)
        self.assertIn('creativeInvoke',self.main.read_text())
        self.assertEqual(receipt['release_accepted'],False)
        self.assertIn(source.LEGACY_ANCHOR,self.main.read_text())
    def test_duplicate_owner_router_anchor_holds_no_mutation(self):
        self.main.write_text(source.ANCHOR+'\\n'+source.ANCHOR+'\\n'+source.LIFECYCLE)
        with self.assertRaisesRegex(ValueError,'ROUTER_OR_LIFECYCLE_DRIFT'):
            source.stage(self.root,self.web.parent)
        self.assertFalse((self.root/'Assets/creative').exists())
        self.assertFalse((self.root/'Integration/CreativeHostBridge.cs').exists())
    def test_corrupt_d02_preflight(self):
        (self.asset/'home.png').write_bytes(b'drift')
        with self.assertRaisesRegex(ValueError,'CANONICAL_D02_SHA_HOLD'):source.stage(self.root,self.web.parent)
        self.unchanged()
    def test_asset_missing_before_write(self):
        (self.web/'studio.html').unlink()
        with self.assertRaisesRegex(ValueError,'ASSETS_INCOMPLETE'):source.stage(self.root,self.web.parent)
        self.unchanged()
    def test_router_anchor_or_file_collision(self):
        self.main.write_text('modified C# router without trusted anchor')
        with self.assertRaisesRegex(ValueError,'ROUTER_OR_LIFECYCLE_DRIFT'):source.stage(self.root,self.web.parent)
        self.assertFalse((self.root/'Assets/creative').exists())
    def test_rollback_on_receipt_conflict(self):
        (self.root.parent/'CREATIVE_STAGE_RECEIPT.json').write_text('owner receipt already exists')
        with self.assertRaisesRegex(ValueError,'RECEIPT_CONFLICT'):source.stage(self.root,self.web.parent)
        self.unchanged()

if __name__=='__main__':unittest.main()