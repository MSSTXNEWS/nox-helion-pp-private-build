#!/usr/bin/env python3
"""Offline fixture regression gates for DeepSeek P0 source; never downloads real weights."""
import hashlib, json, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
import deepseek_owner_range_v10 as m

class Response:
    def __init__(self,data,start,total,url):
        self.status=206
        self.data=data; self.cursor=0; self.url=url
        self.headers={'Content-Range':f'bytes {start}-{start+len(data)-1}/{total}',
                      'Content-Length':str(len(data))}
    def geturl(self):return self.url
    def read(self,size):
        result=self.data[self.cursor:self.cursor+size]
        self.cursor+=len(result);return result
    def __enter__(self):return self
    def __exit__(self,*args):pass

class DeepSeekP0Offline(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'root';self.dst=Path(tmp.name)/'store';self.dst.mkdir()
        (self.root/'state/dispatcher').mkdir(parents=True)
        self.request='1234';self.lease=self.root/'state/dispatcher/lease.json'
        self.lease.write_text(json.dumps({'schema':'NOX_ONEHOST_OWNER_LEASE_V1',
             'instance_id':m.INSTANCE,'owner':'MSSTXNEWS','resource':'p0.model_download',
             'request_id':self.request,'expires_unix':time.time()+90}))
        self.lease.chmod(0o600)
        self.content=b'abcdef0123456789'
        self.name='DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf'
        self.url=f'https://huggingface.co/{m.REPO}/resolve/{m.REVISION}/{self.name}'
        self.row={'path':self.name,'url':self.url,'bytes':len(self.content),
                  'sha256':hashlib.sha256(self.content).hexdigest()}
    def opener(self,request,timeout=30):
        start,end=map(int,request.get_header('Range').split('=')[1].split('-'))
        return Response(self.content[start:end+1],start,len(self.content),self.url)
    def do(self,row=None,limit=m.MAX_RANGE,opener=None):
        return m.download_one(row or self.row,self.dst,self.root,self.lease,
                              self.request,limit=limit,opener=opener or self.opener)
    def test_two_ranges_resume_to_sha_verified_final(self):
        with patch.object(m,'RESERVE',0):
            a=self.do(limit=6);b=self.do(limit=10)
        self.assertEqual((a['state'],a['new_bytes']),('PARTIAL_SHA_PENDING',6))
        self.assertEqual((b['state'],b['new_bytes']),('VERIFIED_FINAL',10))
        self.assertEqual((self.dst/self.name).read_bytes(),self.content)
        self.assertFalse((self.dst/(self.name+'.part')).exists())
        receipt=json.loads((self.dst/(self.name+'.verified.json')).read_text())
        self.assertEqual(receipt['sha256'],self.row['sha256'])
    def test_complete_verified_file_does_not_download(self):
        (self.dst/self.name).write_bytes(self.content)
        self.assertEqual(self.do(opener=lambda *a,**k:self.fail('network used'))['new_bytes'],0)
    def test_existing_corrupt_complete_file_never_overwritten(self):
        (self.dst/self.name).write_bytes(b'X'*len(self.content))
        with self.assertRaisesRegex(m.Hold,'EXISTING_FINAL_UNVERIFIED'):self.do()
    def test_owner_stop_prevents_transfer(self):
        (self.root/'STOP').touch()
        with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):self.do()
    def test_trainer_hold_is_not_global_stop(self):
        (self.root/'state/TRAIN_HOLD.flag').touch()
        with patch.object(m,'RESERVE',0):self.assertEqual(self.do(limit=6)['state'],'PARTIAL_SHA_PENDING')
    def test_lease_request_must_match(self):
        d=json.loads(self.lease.read_text());d['request_id']='different'
        self.lease.write_text(json.dumps(d))
        with self.assertRaisesRegex(m.Hold,'ORIGINAL_LEASE'):self.do()
    def test_lease_parent_traversal_fails_before_file_read(self):
        # A same-owner forged JSON outside dispatcher was admitted by a
        # raw string-prefix path check with dispatcher/../forged.json.
        forged=self.root/'state'/'forged.json'
        forged.write_bytes(self.lease.read_bytes());forged.chmod(0o600)
        escaped=self.root/'state'/'dispatcher'/'..'/'forged.json'
        with self.assertRaisesRegex(m.Hold,'HOLD_LEASE_ORIGIN'):
            m.lease(escaped,self.request,time.time(),self.root)
    def test_lease_absolute_origin_is_mandatory(self):
        with self.assertRaisesRegex(m.Hold,'HOLD_LEASE_ORIGIN'):
            m.lease(Path('state/dispatcher/lease.json'),self.request,time.time(),self.root)
    def test_http_200_cannot_corrupt_partial(self):
        def ignored(request,timeout):
            r=self.opener(request,timeout);r.status=200;return r
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'RANGE_NOT_SUPPORTED'):self.do(opener=ignored)
        self.assertFalse((self.dst/(self.name+'.part')).exists())
    def test_range_offset_and_total_are_exact(self):
        with self.assertRaisesRegex(m.Hold,'RANGE_MISMATCH'):
            m.content_range('bytes 1-3/10',0,2,10)
    def test_redirect_must_be_https_allowlisted(self):
        self.assertFalse(m.final_url_allowed('http://huggingface.co/file'))
        self.assertFalse(m.final_url_allowed('https://attacker.example'))
        self.assertTrue(m.final_url_allowed('https://cas-bridge.xethub.hf.co/abc'))
    def test_full_file_space_and_rollback_reserve(self):
        with patch.object(m,'RESERVE',10**18):
            with self.assertRaisesRegex(m.Hold,'STORAGE_AUTH_OR_SEEKABLE_PLACEMENT'):self.do()
    def test_final_sha_mismatch_not_published(self):
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'FINAL_SHA_MISMATCH'):
                self.do(dict(self.row,sha256='a'*64),limit=16)
        self.assertFalse((self.dst/self.name).exists())
    def test_shared_engram_00006_not_downloadable(self):
        self.assertFalse(m.FILE.fullmatch('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf'))
    def test_manifest_revision_fail_closed(self):
        bad={'schema':'NOX_MODEL_DOWNLOAD_MANIFEST_V1','repository':m.REPO,'revision':'main','files':[]}
        with self.assertRaisesRegex(m.Hold,'MANIFEST_REVISION'):m.load_manifest(json.dumps(bad).encode())
    def test_manifest_sum_matches_engine_p0(self):
        # Actual immutable manifest is fetched from engine stage branch by release controller.
        self.assertEqual(sum([5780704,39535781184,39736712000,39036908384,19923784832,110595290816]),
                         248834257920)


    def test_existing_partial_hardlink_cannot_modify_checkpoint(self):
        preserve=self.dst/'unique-checkpoint';preserve.write_bytes(b'checkpoint-bytes')
        (self.dst/(self.name+'.part')).hardlink_to(preserve)
        with self.assertRaisesRegex(m.Hold,'HARDLINK_PATH'):self.do()
        self.assertEqual(preserve.read_bytes(),b'checkpoint-bytes')
    def test_existing_final_hardlink_is_not_reused(self):
        preserve=self.dst/'unique-model';preserve.write_bytes(self.content)
        (self.dst/self.name).hardlink_to(preserve)
        with self.assertRaisesRegex(m.Hold,'HARDLINK_PATH'):
            self.do(opener=lambda *a,**k:self.fail('network used'))
        self.assertEqual(preserve.read_bytes(),self.content)
    def test_replaced_partial_between_check_and_open_fails_closed(self):
        with patch.object(m,'RESERVE',0):self.do(limit=6)
        partial=self.dst/(self.name+'.part')
        def switched(request,timeout=30):
            partial.unlink()
            partial.write_bytes(self.content[:6])
            return self.opener(request,timeout)
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'PARTIAL_CHANGED'):self.do(opener=switched)
        self.assertEqual(partial.read_bytes(),self.content[:6])
    def test_new_partial_created_during_response_fails_closed(self):
        partial=self.dst/(self.name+'.part')
        def intruder(request,timeout=30):
            partial.write_bytes(b'protected-other-write')
            return self.opener(request,timeout)
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'PARTIAL_CREATE_RACE'):self.do(opener=intruder)
        self.assertEqual(partial.read_bytes(),b'protected-other-write')
    def test_download_lock_hardlink_is_rejected(self):
        preserve=self.dst/'unique-backup';preserve.write_bytes(b'keep')
        (self.dst/'.nox-deepseek-owner.lock').hardlink_to(preserve)
        with self.assertRaisesRegex(m.Hold,'LOCK_FILE_UNSAFE'):self.do()
        self.assertEqual(preserve.read_bytes(),b'keep')


    def test_stop_in_last_read_prevents_partial_success(self):
        def interrupted(request,timeout=30):
            response=self.opener(request,timeout)
            original=response.read
            def read(n):
                chunk=original(n)
                (self.root/'STOP').touch()
                return chunk
            response.read=read
            return response
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):
                self.do(limit=6,opener=interrupted)
        self.assertEqual((self.dst/(self.name+'.part')).read_bytes(),self.content[:6])

    def test_stop_during_complete_reuse_digest_prevents_ack(self):
        final=self.dst/self.name;final.write_bytes(self.content)
        original=m.digest
        def interrupted(path):
            h=original(path);(self.root/'STOP').touch();return h
        with patch.object(m,'digest',side_effect=interrupted):
            with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):
                self.do(opener=lambda *a,**kw:self.fail('unexpected network'))
        self.assertEqual(final.read_bytes(),self.content)

    def test_partial_inode_replacement_after_fsync_fails(self):
        part=self.dst/(self.name+'.part');original=m.stop
        old_fds=[];swapped=[]
        def swap(root):
            if not swapped and part.exists() and part.stat().st_size==6:
                import os
                old_fds.append(os.open(part,os.O_RDONLY))
                part.unlink();part.write_bytes(self.content[:6]);swapped.append(True)
            return original(root)
        try:
            with patch.object(m,'RESERVE',0),patch.object(m,'stop',side_effect=swap):
                with self.assertRaisesRegex(m.Hold,'PARTIAL_LENGTH_RACE'):
                    self.do(limit=6)
        finally:
            import os
            for fd in old_fds:os.close(fd)
        self.assertTrue(swapped)

if __name__=='__main__':unittest.main()
