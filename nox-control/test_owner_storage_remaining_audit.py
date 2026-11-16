"""Bounded metadata/privacy and retained-copy proof tests; no native calls."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
SPEC=importlib.util.spec_from_file_location('remaining_audit',HERE/'owner_storage_remaining_audit.py')
audit=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(audit)


class StorageAudit(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'nox';self.root.mkdir()
        raw=(HERE/'owner_storage_reclaim.py').read_bytes()
        patches=[patch.object(audit,'ROOT',self.root),patch.object(audit,'BUNDLE',{'owner_storage_reclaim.py':base64.b64encode(raw).decode()})]
        for item in patches:item.start();self.addCleanup(item.stop)
        self.helper=audit.helper_module()

    def make(self,name,raw=b'x'*4096):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);return path

    def test_pinned_readonly_helper_rejects_unknown_bytes(self):
        self.assertEqual(hashlib.sha256((HERE/'owner_storage_reclaim.py').read_bytes()).hexdigest(),audit.HELPER_SHA)
        with patch.object(audit,'BUNDLE',{'owner_storage_reclaim.py':base64.b64encode(b'raise Exception()').decode()}):
            with self.assertRaisesRegex(audit.AuditHold,'HELPER_PIN'):audit.helper_module()

    def test_remaining_walk_excludes_already_accounted_scopes_secrets_and_links(self):
        self.make('misc/PRIVATE_CUSTOMER_NAME.dat')
        self.make('lora/runs/checkpoint-1/adapter_model.safetensors')
        self.make('secrets/PRIVATE_KEY_NAME')
        hidden=self.make('state/PRIVATE_RECORD.json')
        (self.root/'misc/alias').symlink_to(hidden)
        value=audit.walk_remaining(self.helper,time.monotonic()+2)
        paths=[row['path'] for row in value['largest']]
        self.assertTrue(any('PRIVATE_CUSTOMER_NAME' in name for name in paths))
        self.assertFalse(any('PRIVATE_KEY_NAME' in name or 'PRIVATE_RECORD' in name or 'checkpoint-1' in name for name in paths))
        self.assertGreaterEqual(value['counts']['symlinks_not_followed'],1)
        self.assertGreaterEqual(value['counts']['sensitive_directories_excluded'],1)

    def test_same_inode_is_counted_once(self):
        first=self.make('misc/first.dat');os.link(first,self.root/'misc/second.dat')
        result=audit.walk_remaining(self.helper,time.monotonic()+2)
        bucket=result['categories']['OTHER_REGULAR_PROTECTED']
        self.assertEqual(bucket['unique_inodes'],1);self.assertEqual(bucket['repeated_inode_paths'],1)
        self.assertEqual(bucket['logical_bytes'],4096)

    def test_two_exact_hashes_require_complete_fresh_process_and_inode_proofs(self):
        raw=b'known adapter fixture';a=self.make('a.safetensors',raw);b=self.make('b.safetensors',raw)
        with patch.object(audit,'BUILDER_BYTES',len(raw)),patch.object(audit,'BUILDER_SHA',audit.digest(raw)), \
             patch.object(audit,'BUILDER_PATHS',(a,b)),patch.object(audit,'HASH_RATE',10**9):
            proof=audit.duplicate_proof(self.helper,time.monotonic()+2)
        self.assertTrue(proof['same_bytes_verified'])
        scan={'ephemeral':[],'largest':[]}
        complete={'complete':True,'used':set(),'active_package_manager':False}
        audit.qualify_results(scan,proof,complete,self.helper)
        self.assertTrue(proof['reviewable_retained_copy_dedup']);self.assertFalse(proof['automatic_deletion_authorized'])
        proof['blockers']=[]
        audit.qualify_results(scan,proof,dict(complete,complete=False),self.helper)
        self.assertFalse(proof['reviewable_retained_copy_dedup'])
        proof['blockers']=[];a.write_bytes(b'changed adapter payload')
        audit.qualify_results(scan,proof,complete,self.helper)
        self.assertIn('BUILDER_IDENTITY_CHANGED_AFTER_HASH',proof['blockers'])
        self.assertFalse(proof['reviewable_retained_copy_dedup'])

    def test_hash_rejects_symlink_or_wrong_full_digest_without_writes(self):
        raw=b'adapter';path=self.make('a.safetensors',raw);link=self.root/'link';link.symlink_to(path)
        with patch.object(audit,'BUILDER_BYTES',len(raw)),patch.object(audit,'BUILDER_SHA','0'*64),patch.object(audit,'HASH_RATE',10**9):
            with self.assertRaisesRegex(audit.AuditHold,'FULL_SHA_MISMATCH'):audit.hash_builder(path,time.monotonic()+2,self.helper)
            with self.assertRaises(self.helper.StorageHold):audit.hash_builder(link,time.monotonic()+2,self.helper)
        self.assertEqual(path.read_bytes(),raw)

    def test_pseudo_reader_handles_size_zero_kernel_scalar_without_loose_paths(self):
        with patch.object(audit,'CGROUP',self.root):
            scalar=self.make('memory.peak',b'175000000000\n')
            self.assertEqual(int(audit.pseudo_bytes(scalar,128)),175000000000)
        with self.assertRaisesRegex(audit.AuditHold,'PSEUDO_SCOPE'):audit.pseudo_bytes(scalar,128)

    def test_slot_projection_rejects_missing_or_conflicting_busy_and_never_exports_prompt(self):
        row={'id':2,'is_processing':True,'id_task':11,'prompt':'PRIVATE_PROMPT','params':{'api_key':'SECRET'},
             'timings':{'prompt_ms':3.4,'prompt_text':'PRIVATE_PROMPT','predicted_n':5}}
        value=audit.slot_projection([row]);self.assertEqual(value['busy'],1)
        self.assertNotIn('PRIVATE',json.dumps(value));self.assertNotIn('SECRET',json.dumps(value))
        for bad in ({'id':2},{'id':2,'is_processing':'false'},{'id':2,'is_processing':False,'processing':True}):
            with self.assertRaises(audit.AuditHold):audit.slot_projection([bad])

    def test_tcp_projection_only_local_client_inode_not_raw_addresses(self):
        header=b'  sl  local_address rem_address st tx rx tr tm retr uid timeout inode\n'
        rows=(b' 0: 0100007F:AC11 0100007F:1F91 01 0:0 0:0 0 0 0 12345\n'
              b' 1: 0100007F:1F91 0100007F:AC11 01 0:0 0:0 0 0 0 23456\n'
              b' 2: 0100000A:AC12 0100007F:1F91 01 0:0 0:0 0 0 0 34567\n')
        self.assertEqual(audit.socket_rows(header+rows),[{'socket_inode':12345,'owners':[]}])

    def test_public_projection_removes_private_paths_and_receipt_is_exclusive_private(self):
        base={key:{} for key in ('coverage','counts','categories','groups','allocation_basis','process_scans',
            'cleanup_refusals','placement','model_client_observation')}
        base.update(schema=audit.SCHEMA,instance_id=audit.INSTANCE,request='123',source_sha='a'*40,state='READ_ONLY',
            started_at=1,finished_at=2,eligible_ephemeral_allocated_bytes=0,files_deleted=0,training_control_performed=False,
            largest=[{'path':'/PRIVATE_OWNER_NAME/file','identity':[1,2],'file_id':'opaque','allocated_bytes':4096}],
            ephemeral_candidates=[],builder_duplicate={'files':[{'path':'/PRIVATE_WEIGHT_PATH','identity':[1,2],'file_id':'fixed'}]})
        public=audit.public_summary(base)
        self.assertNotIn('PRIVATE',json.dumps(public))
        path,sha=audit.write_receipt(self.helper,'123',base)
        self.assertEqual(stat.S_IMODE(Path(path).stat().st_mode),0o600)
        self.assertEqual(audit.digest(Path(path).read_bytes()),sha)
        with self.assertRaises(FileExistsError):audit.write_receipt(self.helper,'123',base)


if __name__=='__main__':unittest.main()
