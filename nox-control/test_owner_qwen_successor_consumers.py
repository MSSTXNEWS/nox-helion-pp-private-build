"""Exact config transitions and predecessor/current proof separation; no native actions."""
import ast
from contextlib import ExitStack
import copy
import hashlib
import importlib.util
from pathlib import Path
import time
import types
import unittest
from unittest.mock import patch

import test_owner_qwen_revision_consumers as prior

HERE = Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location('_successor_test_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

G = load('owner_qwen_successor_guard')
S = load('owner_qwen_successor_status')
M = load('owner_qwen_successor_media_handoff')
R = load('owner_qwen_successor_media_guard')
T = load('owner_qwen_successor_handback_retry')
H = load('owner_qwen_successor_hermes_hydrate')
ORIGIN = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
          'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
PREVIOUS = {'request': '6914959637', 'source_sha': 'a06c6a039ebccd6eaa754914624ab5477beca47b',
            'receipt_sha256': '2f16be7a0bf648621f845c898dd2cc078a98f608fa5b01b3153890c7e3dc41d9'}
NEXT = {'request': '6916000000', 'source_sha': 'c' * 40, 'receipt_sha256': 'd' * 64}
OLD_PINS = {
    'owner_qwen_revision_guard': '6f5aaebaf196c6ec5bd2ad434c5633f457019368568d93b7f71efcc0effcf656',
    'owner_qwen_revision_status': 'c643fe595e09036302818da8e780269ab2e1b48451025b33cb9b491a911eb879',
    'owner_qwen_revision_media_handoff': 'e8fa87f3e84d90fad90030cff9b8e548280b4d3097bde83ba6cedd9f4bef46ce',
    'owner_qwen_revision_media_guard': 'c0feb873174e776285563fdb0290a4b1064402d33c3c05c58d847531690d7723',
    'owner_qwen_revision_handback_retry': '70784355b8458d67f5de0a15b2cce4aaf225fa2522fe90b09f359372ee95fc39',
    'owner_hermes_revision_hydrate': '65daf1acd5dd937e23b9f960dedb720b8259793729115bab153993a282e735a3',
}


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.scope = ExitStack(); self.addCleanup(self.scope.close)
        for module in (G, S, M, H):
            self.scope.enter_context(patch.object(module, 'REVISION_VERIFIER_SHA', 'a' * 64))

    def guard_config(self):
        return prior.G.make_revision_guard_config(prior.G.configuration(ORIGIN, '1' * 64),
                                                  PREVIOUS, OLD_PINS['owner_qwen_revision_guard'])

    def media_config(self):
        old = {'schema': M.CONFIG_SCHEMA, 'enabled': True, 'resume_training_after_media': True,
            'source_sha256': '1' * 64, 'dependencies': M.DEPENDENCIES, 'runtime_sha256': M.MEDIA_SHA,
            'installer_sha256': M.INSTALLER_SHA, 'media_config_sha256': '2' * 64, 'window_admission': ORIGIN}
        return prior.M.make_revision_media_config(old, PREVIOUS, source_sha256=OLD_PINS['owner_qwen_revision_media_handoff'])

    def hydrate_config(self):
        old = {'schema': H.SCHEMA, 'context': {'request': '6910606701', 'source_sha': 'e' * 40},
            'public_repository': H.REPO, 'public_revision': H.REVISION, 'public_filename': H.NAME,
            'bytes': H.SIZE, 'sha256': H.SHA, 'ram_path': str(H.WARM), 'ssd_path': str(H.SSD),
            'minimum_cgroup_headroom_bytes': H.MIN_HEADROOM, 'minimum_tmpfs_reserve_bytes': H.TMPFS_RESERVE,
            'download_source_sha256': H.DOWNLOADER_SHA, 'profile_pins': H.PROFILE_PINS,
            'hydrate_source_sha256': '1' * 64, 'durability': 'VOLATILE_RAM_PUBLIC_REVISION_RESTORABLE', 'new_daemon': False}
        return prior.H.make_revision_hydrate_manifest(old, PREVIOUS,
            source_sha256=OLD_PINS['owner_hermes_revision_hydrate'],
            runtime_entry_sha256='ce7dcbef53c61c63ebab96553ef4c48d9f138a3c426008fa329eb5fd66ee041c')

    def test_guard_preserves_all_quality_policy_and_origin_fields(self):
        old = self.guard_config(); saved = copy.deepcopy(old)
        new = G.make_successor_guard_config(old, NEXT, 'b' * 64)
        self.assertEqual(old, saved)
        self.assertEqual({k: v for k, v in new.items() if k not in ('source_sha256','execution_revision','execution_verifier_sha256')},
                         {k: v for k, v in old.items() if k not in ('source_sha256','execution_revision','execution_verifier_sha256')})
        self.assertEqual(new['execution_revision'], NEXT); self.assertEqual(new['window_admission'], ORIGIN)
        for key, value in (('execution_revision', ORIGIN), ('source_sha256', '0' * 64),
                           ('execution_verifier_sha256', '0' * 64), ('schema', G.CONFIG_SCHEMA)):
            with self.subTest(key=key), self.assertRaises(G.GuardHold):
                G.make_successor_guard_config({**old, key: value}, NEXT, 'b' * 64)
        old['policy']['stale_successful_updates'] = 16
        with self.assertRaises(G.GuardHold): G.make_successor_guard_config(old, NEXT, 'b' * 64)

    def test_media_rebind_never_changes_photo_video_runtime_or_resume_flags(self):
        old = self.media_config(); saved = copy.deepcopy(old)
        new = M.make_successor_media_config(old, NEXT, source_sha256='b' * 64)
        self.assertEqual(old, saved)
        for key in old.keys() - {'source_sha256','execution_revision','execution_verifier_sha256'}:
            self.assertEqual(old[key], new[key])
        for key, value in (('execution_revision', ORIGIN), ('enabled', False), ('resume_training_after_media', False),
                           ('runtime_sha256', '0' * 64), ('window_admission', PREVIOUS)):
            with self.subTest(key=key), self.assertRaises(M.QwenHold):
                M.make_successor_media_config({**old, key: value}, NEXT, source_sha256='b' * 64)

    def test_hydrate_only_rebinds_runtime_without_touching_public_bytes_or_ram_floors(self):
        old = self.hydrate_config(); saved = copy.deepcopy(old)
        new = H.make_successor_hydrate_manifest(old, NEXT, source_sha256='b' * 64, runtime_entry_sha256='c' * 64)
        self.assertEqual(old, saved)
        for key in old.keys() - {'hydrate_source_sha256','profile_pins','execution_revision','execution_verifier_sha256'}:
            self.assertEqual(new[key], old[key])
        self.assertEqual(new['profile_pins'], {**H.PROFILE_PINS, H.REVISION_ENTRY:'c' * 64, 'owner_qwen_execution_revision.py':'a' * 64})
        for key, value in (('minimum_cgroup_headroom_bytes', H.MIN_HEADROOM - 1),
                ('minimum_tmpfs_reserve_bytes', H.TMPFS_RESERVE - 1), ('sha256', '0' * 64),
                ('execution_revision', ORIGIN), ('hydrate_source_sha256', '0' * 64)):
            with self.subTest(key=key), self.assertRaises(H.Hold):
                H.make_successor_hydrate_manifest({**old, key:value}, NEXT, source_sha256='b' * 64, runtime_entry_sha256='c' * 64)

    def test_status_requires_exact_predecessor_and_new_request(self):
        old = {'schema': S.CONFIG_SCHEMA, 'admission': PREVIOUS}
        self.assertEqual(S.make_successor_status_config(old, NEXT), {'schema':S.CONFIG_SCHEMA,'admission':NEXT})
        self.assertEqual(old['admission'], PREVIOUS)
        for before, target in (({**old,'admission':ORIGIN}, NEXT), (old, PREVIOUS)):
            with self.assertRaises(S.StatusHold): S.make_successor_status_config(before, target)


class BootstrapCompatibility(prior.BootstrapTests):
    def setUp(self):
        self.scope = ExitStack(); self.addCleanup(self.scope.close)
        self.scope.enter_context(patch.object(prior, 'G', G))


class MediaCompatibility(prior.MediaTests):
    def setUp(self):
        self.scope = ExitStack(); self.addCleanup(self.scope.close)
        for name, module in (('M',M), ('R',R), ('T',T)):
            self.scope.enter_context(patch.object(prior, name, module))


class StatusProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): prior.F.QwenObservationTests.setUpClass()

    def setUp(self):
        self.fx=prior.F.QwenObservationTests();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.scope=ExitStack();self.addCleanup(self.scope.close)
        self.obs=prior.F.OBS
        self.scope.enter_context(patch.object(S,'BASELINE',{**S.BASELINE,'adapter_tensor_sha256':prior.F.sha(b'tensor5')}))
        for key in ('_revision_context','_revision_verifier'):
            self.addCleanup(lambda key=key:self.obs.__dict__.pop(key,None))

    def fixture(self, initial):
        lineage,saved,manifest,terminal,directory=self.fx.fixture(good=25,skipped=0)
        binding={'fixture_execution': 'predecessor' if initial else 'current'}
        saved['execution_binding']=binding;manifest['execution_binding']=binding
        (directory/'README.md').write_bytes(b'synthetic public card')
        prior.F.write(directory/'student_state.json',saved)
        manifest['files_sha256']={p.name:prior.F.sha(p.read_bytes()) for p in directory.iterdir() if p.name!='checkpoint_manifest.json'}
        pin=prior.F.write(directory/'checkpoint_manifest.json',manifest)
        terminal.update(execution_binding=binding,checkpoint_manifest_sha256=pin)
        prior.F.write(self.fx.output/'owner_last_result.json',terminal)
        result={'initial_anchor':initial,'current_execution':not initial,'legacy_anchor':False,
                'predecessor_reference':PREVIOUS if initial else None,'witness':{'verified':True}}
        verifier=types.SimpleNamespace(activation_status=lambda _: {'active':False},
            checkpoint_binding=lambda *args,**kwargs:copy.deepcopy(result),
            execution_binding=lambda _: {'fixture_execution':'current'})
        ctx={'context':NEXT,'certificate':{'update_evidence':saved['update_evidence'][:6]},
             'execution':{'descriptor':{'anchor':{'directory':directory.name,'manifest_sha256':pin}}}}
        self.obs._revision_context=ctx;self.obs._revision_verifier=verifier
        return lineage,saved,manifest,terminal,directory,pin

    def test_full_predecessor_checkpoint_and_terminal_remain_historical(self):
        lineage,saved,manifest,_,directory,pin=self.fixture(True)
        proof,_,_=S.checkpoint(self.obs,self.fx.contract,lineage,directory.name,pin,time.monotonic()+5)
        self.assertEqual(proof['successful_optimizer_steps'],25)
        self.assertTrue(proof['historical_checkpoint_only']);self.assertFalse(proof['execution_revision_checkpoint_verified'])
        self.assertEqual(proof['execution_revision'],PREVIOUS)
        terminal=S.terminal(self.obs,self.fx.contract,lineage,manifest,saved,time.monotonic()+5)
        self.assertFalse(terminal['current_execution_terminal_verified']);self.assertTrue(terminal['historical_execution'])
        self.assertEqual(terminal['predecessor_execution_revision'],PREVIOUS)

    def test_current_same_counter_checkpoint_does_not_reuse_predecessor_identity(self):
        lineage,saved,manifest,_,directory,pin=self.fixture(False)
        proof,_,_=S.checkpoint(self.obs,self.fx.contract,lineage,directory.name,pin,time.monotonic()+5)
        self.assertFalse(proof['historical_checkpoint_only']);self.assertTrue(proof['execution_revision_checkpoint_verified'])
        self.assertEqual(proof['execution_revision'],NEXT)
        self.assertTrue(S.terminal(self.obs,self.fx.contract,lineage,manifest,saved,time.monotonic()+5)['current_execution_terminal_verified'])
        (directory/'optimizer.pt').write_bytes(b'foreign optimizer')
        with self.assertRaisesRegex(Exception,'FILE_SHA'):
            S.checkpoint(self.obs,self.fx.contract,lineage,directory.name,pin,time.monotonic()+5)

    def test_legacy_false_does_not_mean_current_and_foreign_terminal_is_rejected(self):
        lineage,saved,manifest,terminal,directory,pin=self.fixture(True)
        verifier=self.obs._revision_verifier
        original=verifier.checkpoint_binding
        verifier.checkpoint_binding=lambda *a,**kw: {'legacy_anchor':False,'witness':{}}
        with self.assertRaisesRegex(S.StatusHold,'CHECKPOINT_EXECUTION_SCOPE'):
            S.checkpoint(self.obs,self.fx.contract,lineage,directory.name,pin,time.monotonic()+5)
        verifier.checkpoint_binding=original
        terminal['execution_binding']={'fixture_execution':'unrelated'}
        prior.F.write(self.fx.output/'owner_last_result.json',terminal)
        with self.assertRaisesRegex(S.StatusHold,'PREDECESSOR_TERMINAL_BINDING'):
            S.terminal(self.obs,self.fx.contract,lineage,manifest,saved,time.monotonic()+5)


class SourceScopeTests(unittest.TestCase):
    def test_frozen_sources_unchanged_and_only_renderers_status_projection_differ(self):
        pairs=[('owner_qwen_revision_guard',G,set()),('owner_qwen_revision_media_handoff',M,set()),
               ('owner_qwen_revision_media_guard',R,set()),('owner_qwen_revision_handback_retry',T,set()),
               ('owner_hermes_revision_hydrate',H,set()),('owner_qwen_revision_status',S,{'checkpoint','terminal','snapshot'})]
        for original,module,changed in pairs:
            raw=(HERE/(original+'.py')).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),OLD_PINS[original])
            before={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(raw).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
            after={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(Path(module.__file__).read_bytes()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
            for name in before.keys()-changed:
                self.assertEqual(before[name],after[name],original+':'+name)
            self.assertTrue(all(name.startswith('make_successor_') for name in after.keys()-before.keys()))
        self.assertEqual(G.DEFAULT_POLICY,prior.G.DEFAULT_POLICY)
        self.assertEqual(T.FRESHNESS,prior.T.FRESHNESS)

    def test_new_shared_and_consumer_dependency_hashes_are_coherent(self):
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        verifier=sha(HERE/'owner_qwen_execution_successor.py')
        for module in (G,S,M,H): self.assertEqual(module.REVISION_VERIFIER_SHA,verifier)
        self.assertEqual(R.BASE_SHA,sha(M.__file__))
        self.assertEqual(R.GUARD_SHA,sha(G.__file__))
        self.assertEqual(T.PINS[T.CORE],sha(M.__file__))
        self.assertEqual(T.PINS[T.READER],sha(R.__file__))
        self.assertEqual(T.PINS[T.GUARD],sha(G.__file__))


if __name__=='__main__':unittest.main()
