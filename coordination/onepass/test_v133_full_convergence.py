"""V133 no-loss convergence tests on small synthetic 1089-file fixture, no Vast."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from coordination.onepass import v133_full_convergence as m


class ConvergedWEBV133Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.frozen=root/'frozen.zip'
        self.derived=root/'derived.zip'
        self.kit=root/'pr281.zip'
        self.owner=root/'nox-ui.js'
        self.v132=root/'v132.zip'
        self.out=root/'converged.zip'
        self.choice=b"real choice event UI fixture"
        self.owner.write_bytes(b"known V122 signed owner JS fixture")
        self.v132.write_bytes(b"source-only existing V132 fixture")
        fixed={k:b"<html><head></head><body>original page</body></html>" for k in m.HTML_BASE}
        original={m.OWNER:b"old owner UI"}
        original.update(fixed)
        for page in m.CHOICE_HTML:
            original[page]=b"<html><head></head><body><select class='nx-in'><option>A</option></select></body></html>"
        # The original includes EXACTLY 1089 named site assets; no stubs in production.
        for n in range(1089-len(original)):
            original['site/untouched_asset_%04d.css'%n]=b"body{}"
        self.assertEqual(len(original),1089)
        with zipfile.ZipFile(self.frozen,'w') as z:
            for k,v in sorted(original.items()):z.writestr(k,v)
        changed=dict(original)
        for page in m.CHOICE_HTML:
            changed[page]=changed[page].replace(b"</body>",b"<script src='../../nox-choice-buttons-v293.js'></script></body>")
        changed[m.NEW]=self.choice
        with zipfile.ZipFile(self.derived,'w') as z:
            for k,v in sorted(changed.items()):z.writestr(k,v)
        with zipfile.ZipFile(self.kit,'w') as z:
            for file in m.AUX:z.writestr(file,b"PR281 QA fixture")
        self.overrides={
            "FROZEN_SHA":m.shafile(self.frozen),
            "DERIVED_SHA":m.shafile(self.derived),
            "KIT_SHA":m.shafile(self.kit),
            "OWNER_SHA":m.shafile(self.owner),
            "V132_SHA":m.shafile(self.v132),
            "CHOICE_SHA":m.sha(self.choice)
        }
        self.patches=[patch.object(m,key,value) for key,value in self.overrides.items()]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    def test_all_frozen_paths_preserved_with_exact_rollback(self):
        receipt=m.make(self.frozen,self.derived,self.kit,self.owner,self.v132,self.out)
        self.assertEqual(receipt['state'],"CONVERGED_FULL_WEB_STAGING_SHA_CRC_PASS")
        self.assertEqual(receipt['frozen_paths'],1089)
        self.assertEqual(receipt['changed_original_paths'],9)
        self.assertEqual(receipt['unchanged_original_paths'],1080)
        self.assertFalse(receipt['production_deployed'])
        with zipfile.ZipFile(self.out) as result:
            manifest=json.loads(result.read(m.MANIFEST))
            self.assertEqual(manifest['original_files_deleted'],0)
            self.assertEqual(len(manifest['source_files']),1089)
            self.assertTrue(all(result.read('rollback/'+path) for path in m.CHANGED))
            self.assertEqual(result.read(m.NEW),self.choice)
            self.assertEqual(result.read(m.INTEGRATION),self.v132.read_bytes())
            self.assertFalse(manifest['original_v29_web_92_api_fully_functional'])

    def test_byte_reproducible_at_same_input_sha(self):
        first=m.make(self.frozen,self.derived,self.kit,self.owner,self.v132,self.out)
        second=m.make(self.frozen,self.derived,self.kit,self.owner,self.v132,
                      Path(self.tmp.name)/'again.zip')
        self.assertEqual(first['sha256'],second['sha256'])

    def test_fail_closed_if_original_frozen_hash_drifted(self):
        m.FROZEN_SHA='0'*64
        with self.assertRaisesRegex(ValueError,'HOLD_INPUT_SHA_'):
            m.make(self.frozen,self.derived,self.kit,self.owner,self.v132,self.out)

    def test_fail_closed_on_foreign_pr281_edit(self):
        with zipfile.ZipFile(self.derived) as z:rows={n:z.read(n) for n in z.namelist()}
        rows['site/untouched_asset_0000.css']=b'MALICIOUS'
        with zipfile.ZipFile(self.derived,'w') as z:
            for k,v in sorted(rows.items()):z.writestr(k,v)
        m.DERIVED_SHA=m.shafile(self.derived)
        with self.assertRaisesRegex(ValueError,'HOLD_FOREIGN_DERIVED_DIFF_'):
            m.make(self.frozen,self.derived,self.kit,self.owner,self.v132,self.out)

    def test_existing_bundle_never_overwritten(self):
        self.out.write_bytes(b"ORIGINAL")
        with self.assertRaisesRegex(ValueError,'HOLD_OUTPUT_ALREADY_EXISTS'):
            m.make(self.frozen,self.derived,self.kit,self.owner,self.v132,self.out)
        self.assertEqual(self.out.read_bytes(),b"ORIGINAL")


if __name__=='__main__':unittest.main()
