"""V134 source no-loss fixture, original OneHost static hash and legacy SSE gates."""
from __future__ import annotations
import json,hashlib,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from coordination.onepass import v134_native_owner_compat_converger as m
from coordination.onepass import build_legacy_compat_v2 as compat

class NativeCompatV134(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        d=Path(self.temp.name)
        self.frozen=d/'frozen.zip'
        self.stage=d/'v133.zip'
        self.out=d/'v134.zip'
        self.script=Path('coordination/onepass/nox-legacy-chat-bridge-v293.js')
        self.client=("const rd=r.body.getReader(),dec=new TextDecoder();let buf='',out='',err=null;\n"
            "if(ev.type==='done'&&!out&&ev.note)err=ev.note;\n"
            "if(err&&!out)throw new Error(err);return out};").encode()
        self.frozen_owner=b'frozen owner JS contract'
        self.overlaid_owner=b'V122 response-only owner script'
        original={
            m.OWNER:self.frozen_owner,
            m.SSE_CLIENT:self.client,
        }
        for html in m.PAGES:
            original[html]=b'<html><head></head><body>Owner original page</body></html>'
        # Original V133 changed three independent relative-base pages.
        self.legacy={
            'site/pc/v22/resonance.template.html',
            'site/reference/pc-original-memory.html',
            'site/reference/pc-original-resonance.html'
        }
        for html in self.legacy:
            original[html]=b'<html><head></head><body>Original legacy</body></html>'
        self.choice={
            f'site/pc/pages/{name}/index.html'
            for name in ('cinema','games','graph','music','voice')
        }
        for i in range(1089-len(original)):
            original['site/assets/filler_%04d.css'%i]=b'body{}'
        self.assertEqual(len(original),1089)
        with zipfile.ZipFile(self.frozen,'w') as z:
            for path,blob in sorted(original.items()):z.writestr(path,blob)
        stage=dict(original)
        for x in self.choice:
            stage[x]=stage[x].replace(b'</head>',b'<script src="../../nox-choice-buttons-v293.js" defer></script></head>')
        for x in self.legacy:
            stage[x]=stage[x].replace(b'<head>',b'<head><base href="../">')
        stage[m.OWNER]=self.overlaid_owner
        changed=self.choice|self.legacy|{m.OWNER}
        for x in changed:stage['rollback/'+x]=original[x]
        stage[m.ORIGINAL_V133_MANIFEST]=json.dumps({
            'frozen_sha256':hashlib.sha256(self.frozen.read_bytes()).hexdigest(),
            'original_paths_preserved':1089}).encode()
        # Eight V133 extra members (includes V133 source manifest).
        for i in range(7):stage['integration/extra_%d.json'%i]=b'{}'
        self.assertEqual(len(stage),1106)
        with zipfile.ZipFile(self.stage,'w') as z:
            for p,b in sorted(stage.items()):z.writestr(p,b)
        pins=[
            patch.object(m,'BASE_SHA',m.file_sha(self.stage)),
            patch.object(m,'FROZEN_SHA',m.file_sha(self.frozen)),
            patch.object(m,'OWNER_FROZEN_SHA',m.digest(self.frozen_owner)),
            patch.object(m,'OWNER_V122_SHA',m.digest(self.overlaid_owner)),
            patch.object(m,'KIT_SHA',m.digest(self.client)),
            patch.object(compat,'KIT_SHA',m.digest(self.client))
        ]
        for x in pins:x.start()
        self.addCleanup(lambda:[x.stop() for x in reversed(pins)])

    def test_true_1089_frozen_files_preserved_with_owner_disk_hash(self):
        x=m.build(self.stage,self.frozen,self.script,self.out)
        self.assertEqual(x['state'],'V134_FULL_WEB_SOURCE_SHA_CRC_PASS')
        self.assertEqual(x['total_members'],1125)
        self.assertEqual(x['original_paths_retained'],1089)
        self.assertEqual(x['original_paths_unchanged'],1071)
        self.assertEqual(x['stage_rollback_verified'],16)
        self.assertFalse(x['production_deployed'])
        with zipfile.ZipFile(self.out) as z:
            self.assertEqual(z.read(m.OWNER),self.frozen_owner)
            self.assertEqual(z.read(m.PREVIOUS+m.OWNER),self.overlaid_owner)
            self.assertIn('HOLD_NATIVE_DONE_NOT_VERIFIED',
                          z.read(m.SSE_CLIENT).decode())
            self.assertEqual(z.read(m.NATIVE_SCRIPT),self.script.read_bytes())
            for path in m.PAGES:
                self.assertIn(b'nox-legacy-chat-bridge-v293.js',z.read(path))
                self.assertEqual(z.read(m.PREVIOUS+path),
                                 zipfile.ZipFile(self.stage).read(path))
            meta=json.loads(z.read(m.MANIFEST))
            self.assertFalse(meta['native_owner_deployed'])
            self.assertFalse(meta['all_92_web_e2e_accepted'])
            self.assertTrue(meta['existing_s03_only'])

    def test_byte_identical_repeated_build(self):
        a=m.build(self.stage,self.frozen,self.script,self.out)
        b=m.build(self.stage,self.frozen,self.script,
                  Path(self.temp.name)/'repeat.zip')
        self.assertEqual(a['sha256'],b['sha256'])

    def test_drifted_previous_owner_js_fails_closed(self):
        with patch.object(m,'OWNER_V122_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'HOLD_V122_STATIC_SOURCE_PIN'):
                m.build(self.stage,self.frozen,self.script,self.out)
        self.assertFalse(self.out.exists())

    def test_frozen_source_sha_invalid_holds(self):
        with patch.object(m,'FROZEN_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'HOLD_ORIGINAL_V29_FROZEN_SOURCE_SHA'):
                m.build(self.stage,self.frozen,self.script,self.out)

    def test_existing_artifact_never_overwritten(self):
        self.out.write_bytes(b'owner keeps this')
        with self.assertRaisesRegex(ValueError,'HOLD_SOURCE_OVERWRITE'):
            m.build(self.stage,self.frozen,self.script,self.out)
        self.assertEqual(self.out.read_bytes(),b'owner keeps this')

    def test_untrusted_legacy_client_source_rejected(self):
        with patch.object(m,'KIT_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'HOLD_ORIGINAL_NATIVE_SSE_CLIENT_PIN'):
                m.build(self.stage,self.frozen,self.script,self.out)

    def test_v134_blocker_lives_in_source_fixture_not_workflow(self):
        acceptance=Path('coordination/onepass/NOX_V134_CONVERGED_ACCEPTANCE.json')
        facts=json.loads(acceptance.read_text(encoding='utf8'))
        self.assertEqual(facts['blockers']['vast_noX2_secret'],'HOLD_AUTH_ERROR')

if __name__=='__main__':
    unittest.main()
