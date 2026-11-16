"""Ciphertext-only paging fixtures; no keys generated or native calls."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import owner_checkpoint_backup_pager as pager
import owner_checkpoint_backup_pager_entry as entry


class CheckpointPagerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/dev/shm');self.addCleanup(self.temp.cleanup)
        self.area=Path(self.temp.name)/'pages'
        for item in (patch.object(pager,'AREA',self.area),patch.object(pager,'admission'),
                     patch.object(pager,'stopped',return_value=False)):
            item.start();self.addCleanup(item.stop)
        self.transfer='b'*32;now=int(time.time())
        self.metadata={'transfer_id':self.transfer,'expires_at':now+600}
        encoded='QUJD'*150000;count=len(encoded)//pager.core.CHUNK_CHARS
        manifest={'schema':'NOX_CHECKPOINT_BACKUP_MANIFEST_V1','scope':pager.core.scope(),
            'scope_sha256':pager.core.scope_sha(),'archive_format':'ZIP_STORED','archive_bytes':449984,
            'archive_sha256':'1'*64,'training_resume_tested':False,
            'files':[{'filename':name,'bytes':1000,'sha256':pager.core.RECEIPT_SHA if name=='owner_receipt_step_5.json' else '2'*64}
                     for name in pager.core.NAMES]}
        aad={'schema':'NOX_CHECKPOINT_BACKUP_AAD_V1','algorithm':pager.core.ALGORITHM,
            'manifest':manifest,'manifest_sha256':pager.digest(pager.core.canonical(manifest)),
            'key_id':'3'*64,'transfer_id':self.transfer,'created_at':now,'expires_at':now+600,
            'context':{'request':'123','source_sha':'a'*40},'plaintext_bytes':449984,
            'chunk_chars':pager.core.CHUNK_CHARS,'chunk_count':count,'ciphertext_bytes':450000}
        self.envelope={'schema':'NOX_CHECKPOINT_BACKUP_ENVELOPE_V1','aad':aad,'wrapped_key':'AA==','nonce':'AA==',
            'ciphertext_bytes':450000,'ciphertext_sha256':'4'*64,'ciphertext':encoded}
        outer=pager.digest(pager.core.canonical(self.envelope))
        header={'schema':'NOX_CHECKPOINT_BACKUP_TRANSFER_V1','envelope_sha256':outer,'chunks':count,
            'chunk_chars':pager.core.CHUNK_CHARS,'ciphertext_chars':len(encoded),
            'metadata':{key:value for key,value in self.envelope.items() if key!='ciphertext'}}
        self.rows=[{'kind':'checkpoint_backup_ciphertext_header','data':header}]+[
            {'kind':'checkpoint_backup_ciphertext_chunk','data':{'envelope_sha256':outer,'index':i,'chunks':count,
             'ciphertext':encoded[i*pager.core.CHUNK_CHARS:(i+1)*pager.core.CHUNK_CHARS]}} for i in range(count)]

    def prepare(self):
        with patch.object(pager.core,'public_key_metadata'),patch.object(pager.core,'seal',return_value=self.rows):
            result=pager.prepare(self.metadata,'123','a'*40)
        return result[0]['data']['manifest_sha256'],result

    def test_ciphertext_pages_reassemble_original_envelope_without_protocol_change(self):
        sha,prepared=self.prepare();summary=prepared[0]['data']
        self.assertEqual(summary['page_count'],2);self.assertEqual(summary['chunks_per_page'],6)
        self.assertLess(len(pager.core.canonical(prepared)),16000)
        all_rows=[prepared[1]]
        for index in range(summary['page_count']):
            page=pager.page(self.transfer,sha,index,'456','c'*40)
            self.assertLess(len(pager.core.canonical(page)),390000)
            chunks=[row for row in page if row['kind']=='checkpoint_backup_ciphertext_chunk']
            self.assertLessEqual(len(chunks),6);all_rows.extend(chunks)
            self.assertEqual(page[-1]['data']['files_written'],0)
        self.assertEqual(pager.core.assemble(all_rows)[0],self.envelope)
        folder=self.area/self.transfer
        self.assertEqual({p.name for p in folder.iterdir()},{'ciphertext.b64','manifest.json'})
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in folder.iterdir()))
        self.assertFalse(summary['plaintext_staged_on_native_filesystem'])

    def test_staged_transfer_is_not_overwritten_and_wrong_manifest_pin_is_rejected(self):
        sha,_=self.prepare()
        with patch.object(pager.core,'public_key_metadata'),patch.object(pager.core,'seal') as seal:
            with self.assertRaisesRegex(RuntimeError,'ALREADY_STAGED'):pager.prepare(self.metadata,'789','d'*40)
            seal.assert_not_called()
        with self.assertRaisesRegex(RuntimeError,'MANIFEST_PIN'):pager.page(self.transfer,'0'*64,0,'456','c'*40)
        for index in (-1,True,2):
            with self.assertRaisesRegex(RuntimeError,'PAGE_INDEX'):pager.page(self.transfer,sha,index,'456','c'*40)

    def test_ciphertext_mutation_is_rejected_before_any_page_is_returned(self):
        sha,_=self.prepare();path=self.area/self.transfer/'ciphertext.b64'
        with path.open('r+b') as stream:stream.write(b'X')
        with self.assertRaisesRegex(RuntimeError,'CIPHERTEXT_IDENTITY'):pager.page(self.transfer,sha,0,'456','c'*40)

    def test_expiry_and_owner_stop_cannot_emit_a_page(self):
        sha,_=self.prepare()
        with patch.object(pager.time,'time',return_value=self.metadata['expires_at']+1):
            with self.assertRaisesRegex(RuntimeError,'MANIFEST_SCOPE'):pager.page(self.transfer,sha,0,'456','c'*40)
        with patch.object(pager,'stopped',side_effect=[False,True]):
            with self.assertRaisesRegex(RuntimeError,'OWNER_STOP'):pager.page(self.transfer,sha,0,'456','c'*40)

    def test_stop_reclaimed_during_blocking_pread_never_emits_a_page(self):
        sha,_=self.prepare()
        native_pread=os.pread
        revoked={'active':False}
        def read_then_revoke(*args):
            raw=native_pread(*args)
            revoked['active']=True
            return raw
        with patch.object(pager,'stopped',side_effect=lambda:revoked['active']), \
             patch.object(pager.os,'pread',side_effect=read_then_revoke):
            with self.assertRaisesRegex(RuntimeError,'OWNER_STOP'):
                pager.page(self.transfer,sha,0,'456','c'*40)
        self.assertTrue(revoked['active'])

    def test_unprepared_public_pin_and_bad_module_never_start_child(self):
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40,
                                   'NOX_CHECKPOINT_PAGER_ACTION':'prepare'}), \
             patch.object(entry,'BUNDLE',{}),patch.object(entry.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'BUNDLE_PIN'):entry.main()
            run.assert_not_called()
        compile(entry.CHILD,'<pager-child>','exec')


if __name__=='__main__':unittest.main()
