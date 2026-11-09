"""Real filesystem no-loss exercise of EXPRESS orchestration with isolated owner stubs.
Stubs only replace unavailable Windows/Microsoft owner services; never claim native QA.
"""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'apply_express.py'
spec = importlib.util.spec_from_file_location('express_e06_testable', SOURCE)
EXP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EXP)

class OneShotTest(unittest.TestCase):
    def test_creative_then_chat_then_wow_reaches_output_without_touching_original(self):
        with tempfile.TemporaryDirectory() as sandbox:
            base = Path(sandbox)
            original = base / 'R13' / 'R11'
            original.joinpath('Assets').mkdir(parents=True)
            original.joinpath('NOX.P01.Shell.csproj').write_text('source', encoding='utf-8')
            original.joinpath('Assets/index.html').write_text('before', encoding='utf-8')
            fake = {'home.png': b'original-home', 'menu.png': b'original-menu',
                    'core01.png': b'original-core', 'menu_sections.png': b'original-menu-sections'}
            for name, content in fake.items():
                original.joinpath('Assets',name).write_bytes(content)
            pins = {name: EXP.sha(original/'Assets'/name) for name in fake}
            repo = base / 'repo'
            repo.joinpath('integrations/creative').mkdir(parents=True)
            repo.joinpath('integrations/wow200').mkdir(parents=True)
            order=[]
            def creative_stage(dst, _):
                order.append('creative')
                dst.joinpath('Assets/creative').mkdir(parents=True)
                dst.joinpath('Assets/creative/studio.html').write_text('wow200/runtime/loader.mjs',encoding='utf-8')
                dst.joinpath('MainWindow.xaml.cs').write_text('native bridge',encoding='utf-8')
                return {'files':[{'path':'MainWindow.xaml.cs'}]}
            def chat_stage(dst):
                order.append('chat')
                dst.joinpath('Assets/index.html').write_text("const chatModel=document.getElementById; chatLog.addEventListener",encoding='utf-8')
                proof={'schema':'NOX_E06_R13_CHAT_TDZ_V1'}
                dst.parent.joinpath('E06_CHAT_TDZ_RECEIPT.json').write_text(json.dumps(proof),encoding='utf-8')
                return proof
            def wow_stage(dst, _):
                order.append('wow')
                wow=dst/'Assets/creative/wow200'
                a=wow/'proposals/NOX-CINEMA-FX'
                a.mkdir(parents=True)
                (a/'nox-cinema.mjs').write_text('E01 active',encoding='utf-8')
                (a/'nox-cinema.css').write_text('E01 style',encoding='utf-8')
                old=wow/'legacy/d02-pr30'
                old.mkdir(parents=True)
                (old/'nox-cinema.mjs').write_text('historical original retained',encoding='utf-8')
                runtime=wow/'runtime';runtime.mkdir(parents=True)
                (runtime/'home-scene.mjs').write_text("from '../proposals/NOX-CINEMA-FX/nox-cinema.mjs'",encoding='utf-8')
                (dst/'Assets/index.html').write_text("const chatModel=document.getElementById; chatLog.addEventListener; creative/wow200/runtime/home-scene.mjs; creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.css",encoding='utf-8')
                return {'donor_file_count':56,'active_d02_engine':'OWNER1_PR144_PINNED','legacy_d02_runtime_imported':False,
                        'active_d02_git_blobs':{'js':'tested-owner'}}
            modules={'stage_creative':types.SimpleNamespace(stage=creative_stage),
                     'fix_r13_chat_init':types.SimpleNamespace(stage=chat_stage),
                     'stage_wow200':types.SimpleNamespace(stage=wow_stage)}
            out=base/'out'
            with patch.object(EXP,'D02',pins),patch.dict(sys.modules,modules):
                receipt=EXP.execute(original,repo,out)
            self.assertEqual(order,['creative','chat','wow'])
            self.assertEqual(receipt['wow_donor_files'],56)
            self.assertTrue(receipt['chat_initialization_fixed'])
            self.assertTrue((out/'EXPRESS_RECEIPT.json').is_file())
            self.assertEqual((original/'Assets/index.html').read_text(encoding='utf-8'),'before')
            self.assertFalse((original/'Assets/creative').exists())
            self.assertTrue((out/'R11/Assets/creative/wow200/legacy/d02-pr30/nox-cinema.mjs').exists())

    def test_missing_chat_fix_fails_closed_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'R11';root.joinpath('Assets').mkdir(parents=True)
            (root/'NOX.P01.Shell.csproj').write_text('ok')
            files={'home.png':b'h','menu.png':b'm','core01.png':b'c','menu_sections.png':b's'}
            for name,raw in files.items():(root/'Assets'/name).write_bytes(raw)
            repo=Path(tmp)/'repo';(repo/'integrations/creative').mkdir(parents=True);(repo/'integrations/wow200').mkdir()
            def creative(dst,_):return {'files':[]}
            def broken_chat(dst):return {'schema':'NOX_E06_R13_CHAT_TDZ_V1'}
            called=[]
            def wow(dst,_):called.append(True)
            mods={'stage_creative':types.SimpleNamespace(stage=creative),
                  'fix_r13_chat_init':types.SimpleNamespace(stage=broken_chat),
                  'stage_wow200':types.SimpleNamespace(stage=wow)}
            output=Path(tmp)/'out'
            with patch.object(EXP,'D02',{k:EXP.sha(root/'Assets'/k) for k in files}),patch.dict(sys.modules,mods):
                with self.assertRaisesRegex(ValueError,'CHAT_PREIMAGE_AND_RECEIPT_HOLD'):
                    EXP.execute(root,repo,output)
            self.assertFalse(called)
            self.assertFalse(output.exists())

if __name__=='__main__':unittest.main()