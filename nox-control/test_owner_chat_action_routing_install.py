"""Only temporary files, fake service controls and isolated fixture transports."""
import base64
from contextlib import contextmanager, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import owner_chat_action_routing_install as install

HERE = Path(__file__).resolve().parent
OLD = (HERE / 'owner_chat_stream.py').read_bytes()
NEW = (HERE / 'owner_chat_stream_action_routing.py').read_bytes()


class PairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'owner_chat_stream.py'
        self.staged = self.root / 'exchanged.py'
        self.old_id = install.create(self.target, OLD, 0o644)
        self.new_id = install.create(self.staged, NEW, 0o644)
        self.prepared = {'old_identity': self.old_id, 'new_identity': self.new_id}
        self.context = patch.object(install, 'TARGET', self.target)
        self.context.start(); self.addCleanup(self.context.stop)

    def test_exact_atomic_exchange_and_restore_keep_both_original_inodes(self):
        record = {}; saves = []
        install.apply_source(self.staged, self.prepared, record, lambda: saves.append(dict(record)))
        self.assertTrue(saves[0]['exchange_attempted'])
        self.assertEqual(install.classify_pair(self.staged, self.prepared), 'INSTALLED')
        self.assertEqual(install.read(self.staged), (OLD, self.old_id))
        install.restore_source(self.staged, self.prepared)
        self.assertEqual(install.read(self.target), (OLD, self.old_id))
        self.assertEqual(install.read(self.staged), (NEW, self.new_id))

    def test_kernel_exchange_then_exception_remains_identifiable_and_reversible(self):
        original = install.exchange; record = {}
        def fail_after_move(a, b):
            original(a, b)
            raise OSError('fixture failure after successful kernel operation')
        with patch.object(install, 'exchange', side_effect=fail_after_move):
            with self.assertRaises(OSError):
                install.apply_source(self.staged, self.prepared, record, lambda: None)
        self.assertTrue(record['exchange_attempted'])
        self.assertEqual(install.classify_pair(self.staged, self.prepared), 'INSTALLED')
        install.restore_source(self.staged, self.prepared)
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_same_bytes_foreign_inode_is_not_a_cas_preimage(self):
        other = self.root / 'foreign'
        install.create(other, OLD, 0o644); os.replace(other, self.target)
        foreign = self.target.stat().st_ino
        with self.assertRaisesRegex(install.InstallHold, 'FOREIGN_SOURCE_PAIR'):
            install.apply_source(self.staged, self.prepared, {}, lambda: None)
        self.assertEqual(self.target.stat().st_ino, foreign)
        self.assertEqual(self.staged.read_bytes(), NEW)

    def test_rollback_classifies_foreign_source_before_any_proxy_inspection(self):
        self.target.write_bytes(b'foreign source')
        helper = types.SimpleNamespace(service_state=lambda _: self.fail('no service action before file classification'))
        with self.assertRaisesRegex(install.InstallHold, 'FOREIGN_SOURCE_PAIR'):
            install.rollback_plan(helper, None, {}, None, self.staged, self.prepared, {})

    def test_unsettled_proxy_blocks_rollback_and_original_running_proxy_is_left_alone(self):
        original = {'pid': 9, 'starttime': '10', 'pgrp': 9}
        deploy = types.SimpleNamespace(proxy_identity=lambda _: original)
        for state in ('STOPPING', 'STARTING', 'UNKNOWN', 'BACKOFF'):
            helper = types.SimpleNamespace(service_state=lambda _, s=state: {'state': s})
            with self.subTest(state=state), self.assertRaisesRegex(install.InstallHold, 'UNSETTLED'):
                install.rollback_plan(helper, deploy, original, None, self.staged, self.prepared, {})
        helper = types.SimpleNamespace(service_state=lambda _: {'state': 'RUNNING'})
        self.assertEqual(install.rollback_plan(helper, deploy, original, None, self.staged, self.prepared, {}),
                         {'stop': False, 'start': False, 'restore': False})


class MainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.scripts = self.root / 'scripts'; self.scripts.mkdir()
        (self.root / 'state').mkdir(); (self.root / 'backup').mkdir()
        self.target = self.scripts / 'owner_chat_stream.py'; install.create(self.target, OLD, 0o644)
        self.area = self.root / 'backup/owner_chat_action_routing'
        self.service = 'RUNNING'; self.pid = 100; self.events = []; self.stop_flag_after_stop = False
        @contextmanager
        def lock(_):
            yield
        def proxy(_):
            return {'pid': self.pid, 'starttime': str(self.pid * 10), 'pgrp': self.pid}
        def stop(helper, expected):
            self.events.append('stop'); self.service = 'STOPPED'
            if self.stop_flag_after_stop:
                (self.root / 'STOP').write_bytes(b'owner stop fixture')
        def start(helper):
            self.events.append('start'); self.service = 'RUNNING'; self.pid += 1
            return proxy(helper)
        self.deploy = types.SimpleNamespace(lock=lock, slots_idle=lambda: True,
            model_identity=lambda _: install.MODEL, proxy_identity=proxy, stop_proxy=stop, start_proxy=start)
        self.helper = types.SimpleNamespace(service_state=lambda _: {'state': self.service, 'pid': self.pid if self.service=='RUNNING' else None},
                                            health=lambda: {str(p):200 for p in (8080,8081,8082)})
        self.patches = [patch.object(install, name, val) for name, val in {
            'ROOT':self.root,'SCRIPTS':self.scripts,'STATE':self.root/'state','TARGET':self.target,
            'AREA':self.area,'BUNDLE':{install.CANDIDATE:base64.b64encode(NEW).decode()}}.items()]
        self.patches += [patch.object(install,'load',side_effect=lambda name,pin: self.deploy if name.startswith('owner_download') else self.helper),
            patch.object(install,'snapshots',return_value={'fixture':'preserved'}),
            patch.object(install,'probe',return_value={'module_binding_verified':True,'generation_posts':0,'tool_dispatch_performed':False}),
            patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID':'12345','NOX_OWNER_SOURCE_SHA':'a'*40})]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def run_main(self):
        stream=io.StringIO()
        with redirect_stdout(stream):code=install.main()
        row=next(line for line in stream.getvalue().splitlines() if line.startswith('NOX_MAINT_REPAIR='))
        return code,json.loads(row.split('=',1)[1])['data']

    def test_success_is_source_and_auth_only_and_keeps_private_original(self):
        code,row=self.run_main()
        self.assertEqual(code,0); self.assertEqual(self.events,['stop','start'])
        self.assertEqual(self.target.read_bytes(),NEW)
        self.assertEqual((self.area/'12345/exchanged.py').read_bytes(),OLD)
        self.assertEqual(row['state'],'ROUTING_SOURCE_AND_AUTH_VERIFIED_ACTION_ACCEPTANCE_PENDING')
        self.assertFalse(row['action_execution_acceptance_verified'])
        self.assertEqual(row['training_actions'],0);self.assertEqual(row['generation_posts'],0)
        raw=(self.area/'12345/result.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),row['receipt_sha256'])

    def test_final_acceptance_receipt_failure_compensates_before_success(self):
        original=install.update_private; failed=False
        def update(path,raw,previous):
            nonlocal failed
            if json.loads(raw).get('state','').startswith('ROUTING_SOURCE_') and not failed:
                failed=True;raise OSError('fixture final receipt failed')
            return original(path,raw,previous)
        with patch.object(install,'update_private',side_effect=update):code,row=self.run_main()
        self.assertEqual(code,2);self.assertTrue(row['rollback_verified'])
        self.assertEqual(self.target.read_bytes(),OLD);self.assertEqual(self.service,'RUNNING')
        self.assertEqual(self.events,['stop','start','stop','start'])
        self.assertFalse(row['source_install_verified']);self.assertEqual(row['current_source_sha256'],install.OLD_SHA)

    def test_new_owner_stop_before_write_prevents_source_change_and_restart(self):
        self.stop_flag_after_stop=True
        code,row=self.run_main()
        self.assertEqual(code,2);self.assertEqual(self.events,['stop'])
        self.assertEqual(self.target.read_bytes(),OLD);self.assertTrue((self.root/'STOP').exists())
        self.assertFalse(row['exchange_attempted']);self.assertFalse(row['rollback_verified'])


class ClosureTests(unittest.TestCase):
    def test_candidate_and_both_definition_only_dependencies_are_exact(self):
        self.assertEqual(hashlib.sha256(OLD).hexdigest(),install.OLD_SHA)
        self.assertEqual(hashlib.sha256(NEW).hexdigest(),install.NEW_SHA)
        bundle={n:base64.b64encode((HERE/n).read_bytes()).decode() for n in install.PINS}
        with patch.object(install,'BUNDLE',bundle):
            for name,pin in install.PINS.items():
                self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),pin)
                self.assertTrue(callable(install.load(name,pin).main))
            bundle['owner_native_repair.py']=base64.b64encode(b'raise AssertionError("must not execute")').decode()
            with self.assertRaisesRegex(install.InstallHold,'BUNDLE_PIN'):
                install.load('owner_native_repair.py',install.PINS['owner_native_repair.py'])


if __name__=='__main__':unittest.main()
