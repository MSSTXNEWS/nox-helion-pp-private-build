"""Filesystem transitions and truthful storage evidence, no native services."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent


def module(name):
    spec = importlib.util.spec_from_file_location('_test_' + name, HERE / (name + '.py'))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


class Filesystem(unittest.TestCase):
    def setUp(self):
        self.disk = tempfile.TemporaryDirectory(prefix='nox-cold-test-')
        self.ram = tempfile.TemporaryDirectory(prefix='nox-cold-test-', dir='/dev/shm')
        self.root = Path(self.disk.name); self.ramroot = Path(self.ram.name)
        self.core = module('owner_builder_archive_reclaim'); self.loc = module('owner_builder_cold_location')
        self.entry = module('owner_builder_cold_storage_entry'); self.chat = module('owner_builder_cold_chat_binding')
        self.status = module('owner_download_status')
        self.payload = b'fixture-pinned-builder-weights' * 100
        self.size = len(self.payload); self.digest = hashlib.sha256(self.payload).hexdigest()
        self.canonical = self.root/'canonical'/'adapter_model.safetensors'; self.canonical.parent.mkdir()
        self.alias = self.ramroot/'t724u_builder_best_holdout.safetensors'
        self.state = self.root/'state'; self.state.mkdir()
        self.ramreceipt = self.state/'old_ram_receipt.json'; self.receipt = self.state/'owner_builder_storage_location.json'
        self.canonical.write_bytes(self.payload); self.canonical.chmod(0o666)
        self.alias.write_bytes(self.payload); self.alias.chmod(0o600)
        self.sidecar = self.canonical.parent/'adapter_config.json'; self.sidecar.write_text('{}')
        self.canonical.parent.chmod(0o777)
        parent = self.canonical.parent.stat()
        self.entry.CANONICAL_PARENT_PREIMAGE = {
            key: getattr(parent, key) for key in self.entry.CANONICAL_PARENT_PREIMAGE
        }
        self.backup = self.root/'backup'; self.backup.mkdir(mode=0o700)
        self.backupfd = os.open(self.backup, os.O_RDONLY|os.O_DIRECTORY)
        row = {'role':'builder','filename':self.alias.name,'bytes':self.size,'sha256':self.digest,
               'verified':True,'stat_inode':self.alias.stat().st_ino,'stat_mtime_ns':self.alias.stat().st_mtime_ns}
        self.old = json.dumps({'schema':'NOX_DRIVE_RAM_RECEIPT_V1','state':'RAM_FILES_SHA_VERIFIED_NOT_MERGED','assets':[row]}).encode()
        self.ramreceipt.write_bytes(self.old); self.ramreceipt.chmod(0o600)
        for m in (self.core,self.loc):
            m.ROOT=self.root; m.SIZE=self.size; m.SHA=self.digest; m.CANONICAL=self.canonical
        self.core.STATE=self.state; self.core.RAM=self.alias; self.core.RATE=1024**4
        self.loc.ALIAS=self.alias; self.loc.RECEIPT=self.receipt; self.loc.RAM_RECEIPT=self.ramreceipt
        self.journal={};self.calls=[]
        self.usagepatch=patch.object(self.core,'usage',return_value={'known_reference_count':0,'visibility':'PARTIAL'})
        self.usagepatch.start()

    def tearDown(self):
        self.usagepatch.stop(); os.close(self.backupfd); self.ram.cleanup(); self.disk.cleanup()

    def transition(self, callback=None):
        return self.entry.storage_transition(self.core,self.loc,object(),{},'123','a'*40,self.backupfd,
            time.monotonic()+10,lambda:self.calls.append('preserved'),callback or (lambda:None),self.journal)

    def test_success_retains_bytes_protects_exact_mode_and_publishes_truth(self):
        before=self.canonical.stat(); original_ram=self.alias.stat().st_ino
        result=self.transition()
        self.assertEqual(result['state'],'BUILDER_COLD_ON_SSD_AND_CONSUMERS_VERIFIED')
        self.assertEqual(self.canonical.read_bytes(),self.payload)
        self.assertEqual(self.canonical.stat().st_ino,before.st_ino)
        self.assertEqual(stat.S_IMODE(self.canonical.stat().st_mode),0o644)
        self.assertEqual(stat.S_IMODE(self.canonical.parent.stat().st_mode),0o755)
        self.assertTrue(result['canonical_parent_permission_verified'])
        self.assertFalse(result['other_parent_permissions_changed'])
        self.assertTrue(self.alias.is_symlink());self.assertEqual(os.readlink(self.alias),str(self.canonical))
        self.assertEqual(self.ramreceipt.read_bytes(),self.old)
        self.assertEqual(stat.S_IMODE(self.receipt.stat().st_mode),0o600)
        value=self.loc.locate(rehash=True)
        self.assertEqual(value['state'],'COLD_ON_SSD');self.assertFalse(value['ram_resident'])
        self.assertTrue(self.journal['ram_duplicate_unlinked'])
        self.assertEqual(list((self.ramroot/'.builder-cold-123').iterdir()),[])
        self.assertNotEqual(self.alias.stat().st_ino,original_ram)

    def test_failed_consumer_restores_ram_and_original_permissions(self):
        original=self.alias.stat().st_ino
        def failure(): raise RuntimeError('HOLD_FIXTURE_HTTP')
        with self.assertRaisesRegex(RuntimeError,'HOLD_FIXTURE_HTTP'):self.transition(failure)
        self.assertFalse(self.alias.is_symlink());self.assertEqual(self.alias.stat().st_ino,original)
        self.assertEqual(self.alias.read_bytes(),self.payload);self.assertFalse(self.receipt.exists())
        self.assertEqual(stat.S_IMODE(self.canonical.stat().st_mode),0o666)
        self.assertEqual(stat.S_IMODE(self.canonical.parent.stat().st_mode),0o777)
        self.assertTrue(self.journal['canonical_parent_permission_rollback_verified'])
        self.assertTrue(self.journal['storage_rollback_verified'])

    def test_unknown_parent_identity_holds_and_closes_every_opened_directory(self):
        self.entry.CANONICAL_PARENT_PREIMAGE['st_ino'] += 1
        original = self.core.directory; opened = []
        def observed(path):
            fd = original(path); opened.append(fd); return fd
        with patch.object(self.core, 'directory', side_effect=observed):
            with self.assertRaisesRegex(RuntimeError, 'CANONICAL_PARENT_PREIMAGE'):
                self.transition()
        for fd in set(opened):
            with self.assertRaises(OSError): os.fstat(fd)
        self.assertEqual(stat.S_IMODE(self.canonical.parent.stat().st_mode),0o777)
        self.assertFalse(self.receipt.exists()); self.assertEqual(self.calls,[])

    def test_full_sha_failure_cannot_change_parent_permissions(self):
        self.canonical.write_bytes(b'x' * self.size)
        with self.assertRaisesRegex(RuntimeError, 'HASH_OR_METADATA_CHANGED'):
            self.transition()
        self.assertEqual(stat.S_IMODE(self.canonical.parent.stat().st_mode),0o777)
        self.assertEqual(stat.S_IMODE(self.canonical.stat().st_mode),0o666)
        self.assertFalse((self.backup/'restore-map.json').exists())

    def test_parent_permission_intent_has_private_verified_restore_map(self):
        original = os.fchmod; parent_id = self.canonical.parent.stat().st_ino; witnessed = []
        other_before = {p: self.core.identity(p.stat()) for p in (self.ramroot,self.state)}
        def observed(fd, mode):
            if os.fstat(fd).st_ino == parent_id and stat.S_ISDIR(os.fstat(fd).st_mode):
                raw = (self.backup/'restore-map.json').read_bytes(); value = json.loads(raw)
                self.assertEqual(stat.S_IMODE((self.backup/'restore-map.json').stat().st_mode),0o600)
                self.assertEqual(value['canonical_parent_before']['st_ino'],parent_id)
                self.assertEqual(value['canonical_parent_target_mode'],0o755)
                self.assertEqual(value['canonical_parent_observed_preimage'],self.entry.CANONICAL_PARENT_PREIMAGE)
                self.assertGreaterEqual(len(self.calls),2); witnessed.append(mode)
            return original(fd,mode)
        with patch.object(self.entry.os, 'fchmod', side_effect=observed): self.transition()
        self.assertEqual(witnessed,[0o755])
        for p, before in other_before.items():
            now = self.core.identity(p.stat())
            for key in ('st_dev','st_ino','st_mode','st_uid','st_gid'):
                self.assertEqual(now[key],before[key])

    def test_fsync_failure_after_parent_chmod_rolls_back_exact_mode(self):
        original = os.fsync; parent_id = self.canonical.parent.stat().st_ino; failed = []
        def failing(fd):
            info = os.fstat(fd)
            if info.st_ino == parent_id and stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o755 and not failed:
                failed.append(True); raise OSError('fixture fsync after actual chmod')
            return original(fd)
        with patch.object(self.entry.os, 'fsync', side_effect=failing):
            with self.assertRaisesRegex(OSError, 'fixture fsync'): self.transition()
        self.assertEqual(failed,[True]); self.assertEqual(stat.S_IMODE(self.canonical.parent.stat().st_mode),0o777)
        self.assertEqual(stat.S_IMODE(self.canonical.stat().st_mode),0o666)
        self.assertTrue(self.journal['canonical_parent_permission_rollback_verified'])
        self.assertFalse(self.alias.is_symlink()); self.assertFalse(self.receipt.exists())

    def test_foreign_same_directory_mode_not_overwritten_by_rollback(self):
        def foreign():
            self.canonical.parent.chmod(0o700)
            raise RuntimeError('HOLD_FIXTURE_FOREIGN_PARENT')
        with self.assertRaisesRegex(RuntimeError, 'ROLLBACK_PARENT_FOREIGN'): self.transition(foreign)
        self.assertEqual(stat.S_IMODE(self.canonical.parent.stat().st_mode),0o700)
        self.assertTrue(self.journal['canonical_parent_permission_intent'])
        self.assertFalse(self.journal.get('storage_rollback_verified',not self.journal))
        self.assertNotIn('canonical_parent_permission_rollback_verified',self.journal)

    def test_foreign_named_parent_replacement_not_overwritten_by_rollback(self):
        old = self.root/'detached-canonical'
        def foreign():
            self.canonical.parent.rename(old); self.canonical.parent.mkdir(mode=0o700)
            self.canonical.write_bytes(b'foreign')
            raise RuntimeError('HOLD_FIXTURE_REPLACED_PARENT')
        with self.assertRaisesRegex(RuntimeError, 'PARENT_PATH_CHANGED'): self.transition(foreign)
        self.assertEqual(stat.S_IMODE(self.canonical.parent.stat().st_mode),0o700)
        self.assertEqual(self.canonical.read_bytes(),b'foreign')
        self.assertEqual(stat.S_IMODE(old.stat().st_mode),0o755)

    def test_foreign_alias_is_never_deleted_by_rollback(self):
        def foreign():
            self.alias.unlink();self.alias.write_bytes(b'foreign')
            raise RuntimeError('HOLD_FIXTURE_FOREIGN')
        with self.assertRaisesRegex(RuntimeError,'ROLLBACK_ALIAS_CHANGED'):self.transition(foreign)
        self.assertEqual(self.alias.read_bytes(),b'foreign')
        self.assertEqual((self.ramroot/'.builder-cold-123'/'ram.safetensors').read_bytes(),self.payload)

    def test_canonical_replacement_is_not_silently_trusted(self):
        self.transition();self.canonical.write_bytes(b'x'*self.size)
        with self.assertRaisesRegex(RuntimeError,'CANONICAL_CHANGED|FULL_SHA_CHANGED'):self.loc.locate(rehash=True)

    def test_receipt_mode_and_previous_ram_receipt_remain_strict(self):
        self.transition();self.receipt.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError,'REGULAR_FILE'):self.loc.locate()
        self.receipt.chmod(0o600);self.ramreceipt.write_bytes(self.old+b' ')
        with self.assertRaisesRegex(RuntimeError,'PREVIOUS_RAM_RECEIPT_CHANGED'):self.loc.locate()

    def test_arbitrary_symlink_does_not_receive_exception(self):
        self.transition();self.alias.unlink();self.alias.symlink_to(self.sidecar)
        with self.assertRaisesRegex(RuntimeError,'ALIAS_CHANGED'):self.loc.locate()

    def test_writable_canonical_rejected_without_legacy_mode_exception(self):
        self.transition();self.canonical.chmod(0o666)
        with self.assertRaisesRegex(RuntimeError,'REGULAR_FILE'):self.loc.locate()

    def test_overlay_reports_two_ram_one_ssd_without_private_paths(self):
        self.transition()
        rows=[{'kind':'adapter','role':r,'filename':f,'expected_bytes':self.size,'verified_bytes':self.size,
               'partial_bytes':0,'state':'SHA_VERIFIED_CURRENT_FILE','storage':'RAM'}
              for r,f in [('core_self','core.safetensors'),('intellect','intellect.safetensors')]]
        rows.append({'kind':'adapter','role':'builder','filename':self.alias.name,'expected_bytes':self.size,
                     'verified_bytes':0,'partial_bytes':0,'state':'NOT_OBSERVED','storage':None})
        original={'drive_adapters':self.status.group(rows,{'state':'NATIVE_JOINED_FULL_SHA_RECEIPT'})}
        out=self.chat.overlay_snapshot(original,self.status,self.loc)['drive_adapters']
        self.assertEqual(out['storage_counts'],{'RAM':2,'SSD':1});self.assertEqual(out['verified_files'],3)
        self.assertEqual(out['assets'][2]['location_state'],'COLD_ON_SSD')
        self.assertNotIn(str(self.root),json.dumps(out));self.assertNotIn(str(self.ramroot),json.dumps(out))
        self.assertEqual(original['drive_adapters']['verified_files'],2)

    def test_no_receipt_means_no_cold_promotion(self):
        self.alias.unlink();self.alias.symlink_to(self.canonical)
        row={'role':'builder','filename':self.alias.name,'expected_bytes':self.size,'verified_bytes':0,
             'partial_bytes':0,'state':'NOT_OBSERVED','storage':None}
        original={'drive_adapters':self.status.group([row],{})}
        out=self.chat.overlay_snapshot(original,self.status,self.loc)['drive_adapters']
        self.assertEqual(out['verified_files'],0);self.assertEqual(out['storage_counts']['SSD'],0)


class SourceScope(unittest.TestCase):
    def test_bridge_composition_has_separate_receipts_and_both_replay_guards(self):
        m=module('owner_drive_storage_bridge');raw=(HERE/'owner_drive_ram_bridge.py').read_bytes()
        text=m.compose_consume(raw);compile(text,'<fixture>','exec')
        self.assertIn("STATE / 'storage_consumed'",text)
        self.assertIn("STATE / 'consumed'",text)
        self.assertIn("STATE / 'latest_storage_receipt.json'",text)
        self.assertNotIn("STATE / 'latest_receipt.json'",text)
        self.assertIn('NOX_DRIVE_STORAGE_RECEIPT_V1',text)
        self.assertNotIn("'RAM_FILES_SHA_VERIFIED_NOT_MERGED'",text)
        with self.assertRaisesRegex(RuntimeError,'SOURCE_PIN'):m.compose_consume(raw+b'\n')

    def test_bridge_preserves_admit_and_nonbuilder_path(self):
        wrapper=module('owner_drive_storage_bridge');raw=(HERE/'owner_drive_ram_bridge.py').read_bytes()
        base=module('owner_drive_ram_bridge');original_admit=base.admit;calls=[]
        base.remaining_bytes=lambda manifest:calls.append(manifest) or 17
        base.transfer_asset=lambda *args:{'verified':True,'role':args[0]['role']}
        loc=types.SimpleNamespace(ALIAS=Path('/fixed/builder'),SIZE=10,SHA='a'*64,
            locate=lambda **kw:{'canonical_identity':{'st_ino':1,'st_dev':2,'st_mtime_ns':3},'receipt_sha256':'b'*64})
        wrapper.bind(base,raw,loc)
        self.assertIs(base.admit,original_admit)
        builder={'role':'builder','filename':'builder','bytes':10,'sha256':'a'*64}
        other={'role':'core_self','filename':'core'}
        self.assertEqual(base.remaining_bytes({'assets':[builder,other]}),17)
        self.assertEqual(calls[-1]['assets'],[other])
        row=base.transfer_asset(builder,{}, {},None,time.monotonic()+10)
        self.assertEqual(row['storage'],'SSD');self.assertFalse(row['ram_resident'])
        self.assertEqual(base.transfer_asset(other,{}, {},None,0)['storage'],'RAM')
        with self.assertRaisesRegex(RuntimeError,'BUILDER_ASSET'):
            base.transfer_asset({**builder,'sha256':'c'*64},{},{},None,0)

    def test_exact_js_only_two_replacements_and_frozen_sources(self):
        entry=module('owner_builder_cold_storage_entry');raw=(HERE/'owner-chat-ui.js').read_bytes()
        out=entry.patch_js(raw);self.assertIn('на SSD'.encode(),out)
        self.assertIn('storage_counts'.encode(),out)
        for name,pin in entry.OLD.items():
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),pin)
        with self.assertRaisesRegex(RuntimeError,'JS_PREIMAGE'):entry.patch_js(raw+b'\n')

    def test_all_dependency_pins_and_new_compile(self):
        entry=module('owner_builder_cold_storage_entry')
        for name,pin in {**entry.PINS,**entry.NEW}.items():
            raw=(HERE/name).read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),pin,name)
            compile(raw,name,'exec')
        self.assertNotIn('rearm.main(', (HERE/'owner_builder_cold_storage_entry.py').read_text())

    def test_operator_placeholder_occurs_only_at_bundle_assignment(self):
        raw=(HERE/'owner_builder_cold_storage_entry.py').read_text()
        self.assertEqual(raw.count('__NOX_'+'BUNDLE_JSON__'),1)
        compile(raw.replace('__NOX_'+'BUNDLE_JSON__','{}'),'<operator-injected>','exec')


class SourceRollback(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nox-cold-source-')
        self.path=Path(self.temp.name)/'source.py';self.path.write_bytes(b'old')
        self.m=module('owner_builder_cold_storage_entry');self.calls=[];self.state='RUNNING'
        self.helper=types.SimpleNamespace(service_state=lambda name:self.service(),atomic=self.atomic)
        self.deploy=types.SimpleNamespace(read=lambda p:p.read_bytes(),proxy_identity=lambda helper:{'pid':7},
            stop_proxy=self.stop,start_proxy=self.start)
        self.row={'path':self.path,'old':b'old','new':b'new'}

    def tearDown(self):self.temp.cleanup()
    def service(self):self.calls.append('state');return {'state':self.state}
    def atomic(self,path,raw):self.calls.append('write');path.write_bytes(raw)
    def stop(self,helper,identity):self.calls.append('stop');self.state='STOPPED'
    def start(self,helper):self.calls.append('start');self.state='RUNNING'

    def test_stop_timeout_after_actual_stop_recovers_even_before_first_write(self):
        self.state='STOPPED'
        self.m.rollback_sources(self.deploy,self.helper,[],True,{'pid':7})
        self.assertEqual(self.calls,['state','start'])

    def test_unsettled_stop_preserves_state_without_write_or_start(self):
        self.state='STOPPING';self.path.write_bytes(b'new')
        with self.assertRaisesRegex(RuntimeError,'ROLLBACK_UNSETTLED_PROXY'):
            self.m.rollback_sources(self.deploy,self.helper,[self.row],True,{'pid':7})
        self.assertEqual(self.calls,['state']);self.assertEqual(self.path.read_bytes(),b'new')

    def test_foreign_source_detected_before_any_service_action(self):
        self.path.write_bytes(b'foreign')
        with self.assertRaisesRegex(RuntimeError,'ROLLBACK_FOREIGN_SOURCE'):
            self.m.rollback_sources(self.deploy,self.helper,[self.row],True,{'pid':7})
        self.assertEqual(self.calls,[]);self.assertEqual(self.path.read_bytes(),b'foreign')

    def test_atomic_replace_then_error_intent_restores_owned_source(self):
        self.path.write_bytes(b'new');self.state='STOPPED'
        value=self.m.rollback_sources(self.deploy,self.helper,[self.row],True,{'pid':7})
        self.assertEqual(self.path.read_bytes(),b'old');self.assertEqual(value['owned_writes_restored'],1)
        self.assertEqual(self.calls,['state','write','start'])

    def test_original_running_proxy_with_no_writes_not_restarted(self):
        self.m.rollback_sources(self.deploy,self.helper,[self.row],True,{'pid':7})
        self.assertEqual(self.calls,['state'])


if __name__=='__main__': unittest.main()
