import base64
import copy
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load('staging_entry',HERE/'owner_runtime_source_stage_20261117.py')
builder=load('staging_builder',HERE/'build.py')

def fixture_bundle():
    files={name:"raise RuntimeError('RUNTIME_MUST_NOT_EXECUTE')\n" for name in m.EXPECTED_PATHS}
    return {'files':files,'sha256':{name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}}

class StagingTests(unittest.TestCase):
    def test_safe_idempotent_source_only_stage(self):
        with tempfile.TemporaryDirectory() as td:
            destination=Path(td)/'immutable';bundle=fixture_bundle();sha=m.digest(m.canonical(bundle))
            first=m.stage(bundle,sha,destination=destination)
            before={name:((destination/name).stat().st_ino,(destination/name).stat().st_mtime_ns,(destination/name).read_bytes()) for name in bundle['files']}
            second=m.stage(bundle,sha,destination=destination)
            self.assertEqual(first['status'],'SOURCE_INSTALLED_NOT_BOUND')
            self.assertFalse(first['runtime_imported']);self.assertFalse(first['runtime_bound'])
            self.assertFalse(first['native_chat_canary_pass']);self.assertEqual(first['model_requests'],0)
            self.assertTrue(all(row['created'] for row in first['file_pins']))
            self.assertTrue(all(not row['created'] for row in second['file_pins']))
            self.assertEqual(before,{name:((destination/name).stat().st_ino,(destination/name).stat().st_mtime_ns,(destination/name).read_bytes()) for name in bundle['files']})

    def test_collision_and_symlink_never_overwrite(self):
        bundle=fixture_bundle();sha=m.digest(m.canonical(bundle));first=sorted(bundle['files'])[0]
        for kind in ['bytes','symlink','writable']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                root=Path(td);dest=root/'immutable';target=dest/first;target.parent.mkdir(parents=True)
                sentinel=root/'outside';sentinel.write_bytes(b'KEEP_OUTSIDE')
                if kind=='bytes':target.write_bytes(b'KEEP_COLLISION')
                elif kind=='symlink':target.symlink_to(sentinel)
                else:target.write_bytes(bundle['files'][first].encode());target.chmod(0o666)
                before=target.read_bytes()
                with self.assertRaises((m.Hold,OSError)):m.stage(bundle,sha,destination=dest)
                self.assertEqual(target.read_bytes(),before);self.assertEqual(sentinel.read_bytes(),b'KEEP_OUTSIDE')
                self.assertEqual(len(list(dest.rglob('*.py'))),1)

    def test_input_pin_drift_rejected_before_stage_or_build(self):
        bundle=fixture_bundle();broken=copy.deepcopy(bundle);first=sorted(bundle['files'])[0]
        broken['files'][first]+='# unexpected modification\n'
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);dest=root/'must_not_exist'
            with self.assertRaisesRegex(m.Hold,'HOLD_SOURCE_PIN'):
                m.stage(broken,m.digest(m.canonical(broken)),destination=dest)
            self.assertFalse(dest.exists())
            for prefix,source in [('runtime/nox_integrations','integrations_bridge/nox_integrations'),('runtime/nox_warm','warm_weights_controller/nox_warm')]:
                for name,text in bundle['files'].items():
                    if name.startswith(prefix+'/'):
                        path=root/source/Path(name).name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            lock={'file_pins':bundle['sha256']}
            self.assertEqual(builder.collect_sources(root,lock),bundle['files'])
            changed=root/'integrations_bridge/nox_integrations/__init__.py';changed.write_text('pass\n')
            with self.assertRaisesRegex(ValueError,'INPUT_PIN_DRIFT'):builder.collect_sources(root,lock)

    def test_owner_activity_and_existing_lease_gate(self):
        bundle=fixture_bundle();sha=m.digest(m.canonical(bundle))
        encoded=base64.b64encode(gzip.compress(m.canonical(bundle),mtime=0)).decode()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);state=root/'state';priority=state/'priority';priority.mkdir(parents=True)
            active=priority/'CHAT_ACTIVE';active.write_text('1\n');lock=state/'owner_maintenance.lock';lock.touch(mode=0o600)
            with mock.patch.multiple(m,ROOT=root,BUNDLE_SHA=sha,PACKED_BUNDLE_B64=encoded),mock.patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40}):
                with self.assertRaisesRegex(m.Hold,'HOLD_OWNER_CHAT_ACTIVE_OR_UNKNOWN'):m.run()
                self.assertFalse((root/'extensions').exists());active.write_text('0\n')
                with lock.open('r+') as handle:
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    with self.assertRaisesRegex(m.Hold,'HOLD_MAINTENANCE_BUSY'):m.run()
                    self.assertFalse((root/'extensions').exists())
                    result=m.run(maintenance_lock_fd=handle.fileno())
                    self.assertEqual(result['status'],'SOURCE_INSTALLED_NOT_BOUND')
                    self.assertEqual(result['completion_scope'],'SOURCE_STAGING_ONLY_NOT_CHAT_ACCEPTANCE')
                    self.assertEqual(active.read_text(),'0\n')
                with mock.patch.dict(os.environ,{'NOX_OWNER_SOURCE_SHA':'invalid'}):
                    with self.assertRaisesRegex(m.Hold,'HOLD_OWNER_REQUEST_CONTEXT'):m.run()

if __name__=='__main__':unittest.main()
