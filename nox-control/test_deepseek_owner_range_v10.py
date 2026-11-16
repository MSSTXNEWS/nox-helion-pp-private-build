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
        # Tiny synthetic GGUF fixtures do not occupy the real 248.8GB target.
        volume_fixture=patch.object(m,'MIN_MODEL_VOLUME_BYTES',0)
        volume_fixture.start();self.addCleanup(volume_fixture.stop)
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
    def test_verified_receipt_publish_never_clobbers_previous_owner_evidence(self):
        # A previous transaction's immutable evidence must survive a retry.
        receipt=self.dst/(self.name+'.verified.json')
        original=b'PRIOR-OWNER-SHA-RECEIPT'
        receipt.write_bytes(original)
        with self.assertRaisesRegex(m.Hold,'HOLD_RECEIPT_ALREADY_EXISTS'):
            m.atomic_receipt(receipt,{'schema':'new','sha256':self.row['sha256']})
        self.assertEqual(receipt.read_bytes(),original)
        self.assertFalse(list(self.dst.glob('.nox-ds-v10-*')))
        # Even a dangling target link is occupied and must not be replaced.
        receipt.unlink()
        receipt.symlink_to(self.dst/'nonexistent-owner-receipt')
        with self.assertRaisesRegex(m.Hold,'HOLD_RECEIPT_ALREADY_EXISTS'):
            m.atomic_receipt(receipt,{'schema':'new'})
        self.assertTrue(receipt.is_symlink())
        self.assertFalse(list(self.dst.glob('.nox-ds-v10-*')))

    def test_verified_receipt_new_publish_is_durable_and_unique(self):
        receipt=self.dst/(self.name+'.verified.json')
        document={'schema':'NOX_DEEPSEEK_RANGE_RECEIPT_V10','sha256':self.row['sha256']}
        m.atomic_receipt(receipt,document)
        self.assertEqual(json.loads(receipt.read_text()),document)
        self.assertFalse(list(self.dst.glob('.nox-ds-v10-*')))
        with self.assertRaisesRegex(m.Hold,'HOLD_RECEIPT_ALREADY_EXISTS'):
            m.atomic_receipt(receipt,document)
        self.assertEqual(json.loads(receipt.read_text()),document)

    def test_complete_verified_file_does_not_download(self):
        (self.dst/self.name).write_bytes(self.content)
        self.assertEqual(self.do(opener=lambda *a,**k:self.fail('network used'))['new_bytes'],0)
    def test_reused_complete_final_recovers_missing_receipt_without_download(self):
        # A crash after final link, before receipt publication, must not lose
        # durable SHA evidence or redownload any of the existing GGUF.
        final=self.dst/self.name;final.write_bytes(self.content)
        receipt=self.dst/(self.name+'.verified.json')
        result=self.do(opener=lambda *a,**k:self.fail('unexpected HTTP'))
        self.assertEqual((result['state'],result['new_bytes']),('REUSED_SHA_VERIFIED',0))
        recorded=json.loads(receipt.read_text())
        self.assertEqual((recorded['file'],recorded['sha256'],recorded['new_bytes']),
                         (self.name,self.row['sha256'],0))
        self.assertIs(recorded['recovered_existing'],True)
        old=receipt.read_bytes()
        self.assertEqual(self.do(opener=lambda *a,**k:self.fail('unexpected HTTP'))['new_bytes'],0)
        self.assertEqual(receipt.read_bytes(),old)
        self.assertFalse(list(self.dst.glob('.nox-ds-v10-*')))

    def test_reused_final_rejects_wrong_or_ambiguous_receipt_without_network(self):
        # The final weight may be sound while an existing metadata receipt is
        # damaged/forged. Existence alone cannot certify its provenance.
        final=self.dst/self.name; final.write_bytes(self.content)
        receipt=self.dst/(self.name+'.verified.json')
        doc={'schema':'NOX_DEEPSEEK_RANGE_RECEIPT_V10','request':self.request,
             'file':self.name,'bytes':self.row['bytes'],
             'sha256':self.row['sha256'],'new_bytes':0,'at_unix':time.time()}
        good=json.dumps(doc)
        cases=[
            ('wrong_sha', json.dumps(dict(doc,sha256='0'*64)), 'HOLD_RECEIPT_IDENTITY'),
            ('wrong_file', json.dumps(dict(doc,file='unexpected.gguf')), 'HOLD_RECEIPT_IDENTITY'),
            ('wrong_bytes', json.dumps(dict(doc,bytes=len(self.content)+1)), 'HOLD_RECEIPT_IDENTITY'),
            ('bool_bytes', json.dumps(dict(doc,bytes=True)), 'HOLD_RECEIPT_IDENTITY'),
            ('missing_schema', json.dumps(dict(doc,schema='WRONG')), 'HOLD_RECEIPT_IDENTITY'),
            ('invalid_request', json.dumps(dict(doc,request='other-owner')), 'HOLD_RECEIPT_IDENTITY'),
            ('duplicate_key', good[:-1]+', "sha256":"'+doc['sha256']+'"}', 'HOLD_RECEIPT_DUPLICATE_KEY'),
            ('nonfinite', good[:-1]+', "extension":NaN}', 'HOLD_RECEIPT_NONFINITE'),
            ('infinite_float', good.replace('"at_unix": '+str(doc['at_unix']), '"at_unix": 1e999'),
             'HOLD_RECEIPT_IDENTITY'),
            ('truncated', good[:-1], 'HOLD_RECEIPT_INVALID_JSON'),
            ('oversized', good[:-1]+', "extra":"'+('X'*8192)+'"}', 'HOLD_RECEIPT_SIZE'),
        ]
        for name,wire,reason in cases:
            with self.subTest(case=name):
                receipt.write_bytes(wire.encode())
                with self.assertRaisesRegex(m.Hold,reason):
                    self.do(opener=lambda *a,**k:self.fail('network on ambiguous receipt'))
                self.assertEqual(final.read_bytes(),self.content)
                self.assertEqual(receipt.read_bytes(),wire.encode())

    def test_reused_final_receipt_fifo_swap_cannot_hang(self):
        import os
        final=self.dst/self.name; final.write_bytes(self.content)
        receipt=self.dst/(self.name+'.verified.json')
        receipt.write_text(json.dumps({
            'schema':'NOX_DEEPSEEK_RANGE_RECEIPT_V10','request':self.request,
            'file':self.name,'bytes':self.row['bytes'],
            'sha256':self.row['sha256'],'new_bytes':0,'at_unix':time.time()}))
        real_open=os.open
        swapped=[]
        def race(path,flags,*args,**kwargs):
            if Path(path)==receipt and not swapped:
                self.assertTrue(flags & os.O_NONBLOCK)
                receipt.unlink();os.mkfifo(receipt);swapped.append(True)
            return real_open(path,flags,*args,**kwargs)
        with patch.object(m.os,'open',side_effect=race):
            with self.assertRaisesRegex(m.Hold,'HOLD_RECEIPT_CHANGED'):
                self.do(opener=lambda *a,**k:self.fail('no network after receipt race'))
        self.assertTrue(swapped)
        self.assertEqual(final.read_bytes(),self.content)

    def test_reused_final_dangling_receipt_is_never_replaced(self):
        final=self.dst/self.name;final.write_bytes(self.content)
        receipt=self.dst/(self.name+'.verified.json')
        receipt.symlink_to(self.dst/'missing-owner-receipt')
        with self.assertRaisesRegex(m.Hold,'HOLD_SYMLINK_PATH'):
            self.do(opener=lambda *a,**k:self.fail('unexpected HTTP'))
        self.assertTrue(receipt.is_symlink())
        self.assertFalse(list(self.dst.glob('.nox-ds-v10-*')))

    def test_existing_corrupt_complete_file_never_overwritten(self):
        (self.dst/self.name).write_bytes(b'X'*len(self.content))
        with self.assertRaisesRegex(m.Hold,'EXISTING_FINAL_UNVERIFIED'):self.do()
    def test_owner_stop_inventory_is_metadata_only_and_never_claims_sha(self):
        # A size match (even for a corrupt GGUF) is not a verified digest.
        # Read-only owner maintenance must never trigger a 110GB SHA scan.
        final=self.dst/self.name
        final.write_bytes(b'X'*len(self.content))
        (self.root/'STOP').touch()
        with patch.object(m,'digest',side_effect=AssertionError('unleased SHA scan')):
            rows=m.inventory({self.name:self.row},self.dst)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['present_bytes'],len(self.content))
        self.assertTrue(rows[0]['metadata_complete'])
        self.assertFalse(rows[0]['verified'])
        self.assertEqual(rows[0]['verification_scope'],'SHA_UNCHECKED')

    def test_full_model_capacity_blocks_a_partial_download_before_network(self):
        # Current shard fits (16 B < 35 B), but other pinned shards cannot.
        # Per-shard admission alone could strand the model on an undersized disk.
        from types import SimpleNamespace
        other = 'DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf'
        tiny = {self.name: (len(self.content), self.row['sha256']),
                other: (25, 'a' * 64)}
        vfs = SimpleNamespace(f_bavail=35, f_frsize=1, f_blocks=120)
        with patch.object(m, 'PINNED_FILE_FACTS', tiny), \
             patch.object(m, 'MIN_MODEL_VOLUME_BYTES', 50), \
             patch.object(m, 'RESERVE', 0), \
             patch.object(m.os, 'statvfs', return_value=vfs):
            with self.assertRaisesRegex(m.Hold, 'HOLD_STORAGE_INSUFFICIENT_FOR_COMPLETE_MODEL'):
                self.do(opener=lambda *a, **k: self.fail('network must not start'))
        self.assertFalse((self.dst / (self.name + '.part')).exists())

    def test_full_model_capacity_allows_already_allocated_partial_resume(self):
        from types import SimpleNamespace
        other = 'DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf'
        tiny = {self.name: (len(self.content), self.row['sha256']),
                other: (25, 'a' * 64)}
        part = self.dst / (self.name + '.part')
        part.write_bytes(self.content[:8])
        # 8 existing bytes are allocated, leaving 8+25 = 33 B of growth.
        vfs = SimpleNamespace(f_bavail=35, f_frsize=1, f_blocks=120)
        with patch.object(m, 'PINNED_FILE_FACTS', tiny), \
             patch.object(m, 'MIN_MODEL_VOLUME_BYTES', 50), \
             patch.object(m, 'RESERVE', 0), \
             patch.object(m.os, 'statvfs', return_value=vfs):
            result = self.do(limit=8)
        self.assertEqual(result['state'], 'VERIFIED_FINAL')
        self.assertEqual(result['new_bytes'], 8)
        self.assertEqual((self.dst / self.name).read_bytes(), self.content)

    def test_owner_stop_prevents_transfer(self):
        (self.root/'STOP').touch()
        with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):self.do()
    def test_owner_maintenance_blocks_exact_deepseek_transfer(self):
        # Maintenance is an owner fence even if every legacy STOP name is absent.
        flag=self.root/'state/OWNER_MAINTENANCE.flag'
        flag.touch()
        with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):
            self.do(opener=lambda *a,**kw:self.fail('maintenance must not download'))
        flag.unlink()
        flag.symlink_to(self.root/'unavailable-target')
        with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):
            self.do(opener=lambda *a,**kw:self.fail('dangling owner maintenance must not download'))
        self.assertFalse((self.dst/(self.name+'.part')).exists())

    def test_dangling_workspace_stop_fails_closed(self):
        # lstat identifies even a dangling owner STOP symlink; no network call.
        original=m.os.lstat
        def simulated(path,*args,**kwargs):
            if str(path)=='/workspace/NOX_STOP':
                return object()
            return original(path,*args,**kwargs)
        with patch.object(m.os,'lstat',side_effect=simulated):
            with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):
                m.stop(self.root)

    def test_unreadable_owner_stop_is_not_mistaken_for_absence(self):
        # EACCES/ELOOP on any owner flag must prevent Range network and writes.
        original=m.os.lstat
        flags=(self.root/'STOP',self.root/'state/OWNER_MAINTENANCE.flag',
               Path('/workspace/NOX_STOP'))
        for blocked in flags:
            with self.subTest(flag=str(blocked)):
                def denied(path,*args,**kwargs):
                    if Path(path)==blocked:
                        raise PermissionError(13,'owner STOP not readable',str(blocked))
                    return original(path,*args,**kwargs)
                with patch.object(m.os,'lstat',side_effect=denied),patch.object(m,'RESERVE',0):
                    with self.assertRaisesRegex(m.Hold,'HOLD_OWNER_STOP_UNREADABLE'):
                        self.do(opener=lambda *a,**kw:self.fail('network on unreadable STOP'))
                self.assertFalse((self.dst/(self.name+'.part')).exists())

    def test_owner_stop_symlink_loop_is_not_mistaken_for_absence(self):
        import errno
        original=m.os.lstat
        blocked=self.root/'state/STOP.flag'
        def loop(path,*args,**kwargs):
            if Path(path)==blocked:
                raise OSError(errno.ELOOP,'unsafe owner STOP path',str(blocked))
            return original(path,*args,**kwargs)
        with patch.object(m.os,'lstat',side_effect=loop):
            with self.assertRaisesRegex(m.Hold,'HOLD_OWNER_STOP_UNREADABLE'):
                m.stop(self.root)

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
    def test_ambiguous_owner_lease_json_never_admits_a_download(self):
        # JSON default last-key-wins can disagree with another lease reader.
        valid=self.lease.read_text()
        original=json.loads(valid)
        cases={
            'duplicate_root':valid[:-1]+',"owner":"MSSTXNEWS"}',
            'duplicate_nested':json.dumps(dict(original, note=json.loads('{"x":1,"x":2}'))),
            'nonfinite':valid[:-1]+',"unused":NaN}',
            'malformed':'{"owner":',
            'array':'[]',
        }
        # Preserve the duplicate nested keys on the wire instead of round-tripping.
        cases['duplicate_nested']=valid[:-1]+',"note":{"x":1,"x":2}}'
        for label,wire in cases.items():
            with self.subTest(label=label):
                self.lease.write_text(wire)
                with self.assertRaises(m.Hold) as error:
                    self.do(opener=lambda *a,**k:self.fail('network on invalid owner lease'))
                self.assertIn(str(error.exception), (
                    'HOLD_LEASE_DUPLICATE_KEY', 'HOLD_LEASE_NONFINITE_JSON',
                    'HOLD_LEASE_INVALID_JSON', 'HOLD_LEASE_SCHEMA'))
                self.assertFalse((self.dst/(self.name+'.part')).exists())
        self.lease.write_text(valid)
        with patch.object(m,'RESERVE',0):
            self.assertEqual(self.do(limit=6)['state'],'PARTIAL_SHA_PENDING')

    def test_lease_symlink_swap_during_open_is_never_followed(self):
        # The lstat precheck cannot authorize a different file opened later.
        forged=self.root/'state/forged.json'
        forged.write_bytes(self.lease.read_bytes());forged.chmod(0o600)
        real_open=m.os.open
        def swapped(path, flags, *args, **kwargs):
            if Path(path)==self.lease:
                self.lease.unlink()
                self.lease.symlink_to(forged)
            return real_open(path,flags,*args,**kwargs)
        with patch.object(m.os,'open',side_effect=swapped):
            with self.assertRaisesRegex(m.Hold,'HOLD_LEASE_UNREADABLE'):
                m.lease(self.lease,self.request,time.time(),self.root)
        self.assertTrue(self.lease.is_symlink())
        self.assertEqual(forged.read_bytes(),forged.read_bytes())

    def test_lease_replaced_during_fd_read_holds_even_with_valid_json(self):
        successor=self.root/'state/dispatcher/successor.json'
        successor.write_bytes(self.lease.read_bytes());successor.chmod(0o600)
        real_read=m.os.read
        def replaced(fd, size):
            raw=real_read(fd,size)
            successor.replace(self.lease)
            return raw
        with patch.object(m.os,'read',side_effect=replaced):
            with self.assertRaisesRegex(m.Hold,'HOLD_LEASE_FILE_CHANGED'):
                m.lease(self.lease,self.request,time.time(),self.root)

    def test_lease_mutated_in_place_during_fd_read_holds(self):
        real_read=m.os.read
        def mutated(fd,size):
            raw=real_read(fd,size)
            self.lease.write_bytes(b'{}')
            return raw
        with patch.object(m.os,'read',side_effect=mutated):
            with self.assertRaisesRegex(m.Hold,'HOLD_LEASE_FILE_CHANGED'):
                m.lease(self.lease,self.request,time.time(),self.root)

    def test_invalid_http_content_length_holds_before_partial_write(self):
        for malformed in ('NaN','+16','1.0','not-a-number','9'*200,''):
            with self.subTest(header=malformed[:20]):
                def bad_response(request,timeout):
                    response=self.opener(request,timeout)
                    response.headers['Content-Length']=malformed
                    return response
                with patch.object(m,'RESERVE',0):
                    with self.assertRaisesRegex(m.Hold,'HOLD_HTTP_LENGTH'):
                        self.do(opener=bad_response)
                self.assertFalse((self.dst/(self.name+'.part')).exists())

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
    def test_physically_undersized_volume_blocks_before_any_http(self):
        # The 183GB original disk can fit a single 39GB shard but never the
        # complete 248.8GB model. Fail before network or part allocation.
        from types import SimpleNamespace
        small_volume=SimpleNamespace(f_blocks=180*1024**3,
                                     f_bavail=80*1024**3,f_frsize=1)
        with patch.object(m,'MIN_MODEL_VOLUME_BYTES',248834257920), \
             patch.object(m,'RESERVE',0), \
             patch.object(m.os,'statvfs',return_value=small_volume):
            with self.assertRaisesRegex(m.Hold,'HOLD_STORAGE_TOTAL_CAPACITY'):
                self.do(opener=lambda *a,**kw:self.fail('network forbidden'))
        self.assertFalse((self.dst/(self.name+'.part')).exists())

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
    def test_rebalanced_tampered_manifest_holds(self):
        """Pin every digest and size: a valid total and revision do not certify shards."""
        files=[{'path':name,'bytes':size,'sha256':sha,
                'url':f'https://huggingface.co/{m.REPO}/resolve/{m.REVISION}/{name}'}
               for name,(size,sha) in m.PINNED_FILE_FACTS.items()]
        manifest={'schema':'NOX_MODEL_DOWNLOAD_MANIFEST_V1',
                  'repository':m.REPO,'revision':m.REVISION,'files':files,
                  'total_unique_gguf_bytes':248834257920,
                  'alias':{'path':'DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf',
                           'target':'DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf',
                           'duplicate_bytes':False}}
        self.assertEqual(len(m.load_manifest(json.dumps(manifest).encode())),6)
        files[1]['sha256']='0'*64
        with self.assertRaisesRegex(m.Hold,'HOLD_MANIFEST_FILE_IDENTITY'):
            m.load_manifest(json.dumps(manifest).encode())
        files[1]['sha256']=m.PINNED_FILE_FACTS[files[1]['path']][1]
        files[1]['bytes']+=1
        files[2]['bytes']-=1
        with self.assertRaisesRegex(m.Hold,'HOLD_MANIFEST_FILE_IDENTITY'):
            m.load_manifest(json.dumps(manifest).encode())

    def test_manifest_rejects_duplicate_keys_nonfinite_and_malformed_json(self):
        """An ambiguous manifest must fail before any network or owner admission."""
        files = [
            {'path': name, 'bytes': size, 'sha256': sha,
             'url': f'https://huggingface.co/{m.REPO}/resolve/{m.REVISION}/{name}'}
            for name, (size, sha) in m.PINNED_FILE_FACTS.items()
        ]
        manifest = {
            'schema': 'NOX_MODEL_DOWNLOAD_MANIFEST_V1',
            'repository': m.REPO, 'revision': m.REVISION,
            'files': files, 'total_unique_gguf_bytes': 248834257920,
            'alias': {
                'path': 'DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf',
                'target': 'DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf',
                'duplicate_bytes': False,
            },
        }
        good = json.dumps(manifest)
        self.assertEqual(len(m.load_manifest(good)), 6)
        ambiguous = (
            (good.replace('{"schema":', '{"revision": "main", "schema":', 1),
             'HOLD_MANIFEST_DUPLICATE_KEY'),
            (good.replace('"bytes": 5780704', '"bytes": 1, "bytes": 5780704', 1),
             'HOLD_MANIFEST_DUPLICATE_KEY'),
            (good.replace('"duplicate_bytes": false',
                          '"duplicate_bytes": true, "duplicate_bytes": false', 1),
             'HOLD_MANIFEST_DUPLICATE_KEY'),
            (good[:-1] + ', "extension": NaN}', 'HOLD_MANIFEST_NONFINITE_JSON'),
            (good[:-1] + ', "extension": Infinity}', 'HOLD_MANIFEST_NONFINITE_JSON'),
            (good[:-1], 'HOLD_MANIFEST_INVALID_JSON'),
        )
        for payload, reason in ambiguous:
            with self.subTest(reason=reason, payload_tail=payload[-55:]):
                with self.assertRaisesRegex(m.Hold, reason):
                    m.load_manifest(payload.encode('utf-8'))

    def test_manifest_sum_matches_engine_p0(self):
        # Actual immutable manifest is fetched from engine stage branch by release controller.
        self.assertEqual(sum([5780704,39535781184,39736712000,39036908384,19923784832,110595290816]),
                         248834257920)


    def test_looping_or_unreadable_part_metadata_never_counted_as_missing(self):
        # On Python 3.13 Path.exists()/is_symlink() suppress ELOOP and can
        # misclassify an unreadable existing .part as a genuinely absent one.
        import errno
        part = self.dst / (self.name + '.part')
        part.write_bytes(b'unique-owner-partial')
        original = m.os.lstat
        for failure in (errno.ELOOP, errno.EACCES):
            with self.subTest(errno=failure):
                def inaccessible(path, *args, **kwargs):
                    if Path(path) == part:
                        raise OSError(failure, 'metadata unavailable', str(path))
                    return original(path, *args, **kwargs)
                with patch.object(m.os, 'lstat', side_effect=inaccessible), patch.object(m, 'RESERVE', 0):
                    with self.assertRaisesRegex(m.Hold, 'HOLD_PATH_UNREADABLE'):
                        self.do(opener=lambda *a, **kw: self.fail('download on unknown metadata'))
                self.assertEqual(part.read_bytes(), b'unique-owner-partial')

    def test_unreadable_parent_metadata_holds_before_network(self):
        import errno
        original = m.os.lstat
        def inaccessible(path, *args, **kwargs):
            if Path(path) == self.dst:
                raise OSError(errno.EACCES, 'parent metadata inaccessible', str(path))
            return original(path, *args, **kwargs)
        with patch.object(m.os, 'lstat', side_effect=inaccessible), patch.object(m, 'RESERVE', 0):
            with self.assertRaisesRegex(m.Hold, 'HOLD_PATH_UNREADABLE'):
                self.do(opener=lambda *a, **kw: self.fail('network on blocked parent'))
        self.assertFalse((self.dst / (self.name + '.part')).exists())

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
        # STOP raised while response.read() was blocked: do not append those
        # six newly received bytes even though the response returned them.
        self.assertEqual((self.dst/(self.name+'.part')).read_bytes(),b'')

    def test_lease_expires_during_range_read_never_appends(self):
        def interrupted(request,timeout=30):
            response=self.opener(request,timeout)
            original=response.read
            def read(n):
                chunk=original(n)
                lease_data=json.loads(self.lease.read_text())
                lease_data['expires_unix']=time.time()-1
                self.lease.write_text(json.dumps(lease_data))
                return chunk
            response.read=read
            return response
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'ORIGINAL_LEASE'):
                self.do(limit=6,opener=interrupted)
        self.assertEqual((self.dst/(self.name+'.part')).read_bytes(),b'')

    def test_stop_during_complete_reuse_digest_prevents_ack(self):
        final=self.dst/self.name;final.write_bytes(self.content)
        original=m.digest
        def interrupted(path):
            h=original(path);(self.root/'STOP').touch();return h
        with patch.object(m,'digest',side_effect=interrupted):
            with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):
                self.do(opener=lambda *a,**kw:self.fail('unexpected network'))
        self.assertEqual(final.read_bytes(),self.content)

    def test_final_publication_never_overwrites_racing_owner_file(self):
        # Existing final is absent at initial admission. Another writer publishes
        # it immediately after our final.exists() guard: os.replace lost it.
        final=self.dst/self.name
        partial=self.dst/(self.name+'.part')
        original_exists=Path.exists
        calls={'final':0}
        def race_exists(path):
            if path==final:
                calls['final']+=1
                if calls['final']==1:
                    final.write_bytes(b'other-owner-unique-checkpoint')
                    return False
            return original_exists(path)
        with patch.object(m,'RESERVE',0),patch.object(Path,'exists',new=race_exists):
            with self.assertRaisesRegex(m.Hold,'HOLD_FINAL_RACE'):
                self.do(limit=len(self.content))
        self.assertEqual(final.read_bytes(),b'other-owner-unique-checkpoint')
        self.assertEqual(partial.read_bytes(),self.content)
        self.assertFalse((self.dst/(self.name+'.verified.json')).exists())

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


    def test_complete_partial_after_crash_publishes_without_network_or_double_copy(self):
        partial=self.dst/(self.name+'.part')
        partial.write_bytes(self.content)
        with patch.object(m,'RESERVE',0):
            result=self.do(opener=lambda *a,**kw:self.fail('must not redownload a complete partial'))
        self.assertEqual((result['state'],result['new_bytes']),('VERIFIED_FINAL',0))
        self.assertEqual((self.dst/self.name).read_bytes(),self.content)
        self.assertFalse(partial.exists())
        self.assertEqual(json.loads((self.dst/(self.name+'.verified.json')).read_text())['new_bytes'],0)

    def test_corrupt_complete_partial_fails_without_network_or_publishing(self):
        partial=self.dst/(self.name+'.part')
        partial.write_bytes(b'X'*len(self.content))
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'FINAL_SHA_MISMATCH'):
                self.do(opener=lambda *a,**kw:self.fail('must not fetch a corrupt full partial'))
        self.assertEqual(partial.read_bytes(),b'X'*len(self.content))
        self.assertFalse((self.dst/self.name).exists())

    def test_oversized_partial_is_protected_without_network(self):
        partial=self.dst/(self.name+'.part')
        partial.write_bytes(self.content+b'extra')
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'PARTIAL_ABOVE_TOTAL'):
                self.do(opener=lambda *a,**kw:self.fail('must not fetch oversized partial'))
        self.assertEqual(partial.read_bytes(),self.content+b'extra')

    def test_owner_state_stop_flag_blocks_full_partial_promotion(self):
        partial=self.dst/(self.name+'.part')
        partial.write_bytes(self.content)
        (self.root/'state/STOP.flag').touch()
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'OWNER_STOP'):
                self.do(opener=lambda *a,**kw:self.fail('STOP must stop the network'))
        self.assertEqual(partial.read_bytes(),self.content)
        self.assertFalse((self.dst/self.name).exists())


    def test_raced_fifo_in_existing_final_hash_fails_without_blocking(self):
        """A metadata-valid GGUF changed to a FIFO must never stall the SHA scan."""
        import os
        final=self.dst/self.name
        final.write_bytes(self.content)
        opened=os.open
        hit=[]
        def swap(path,flags,*args,**kwargs):
            if Path(path)==final and not hit:
                self.assertTrue(flags & os.O_NONBLOCK)
                final.unlink();os.mkfifo(final);hit.append(True)
            return opened(path,flags,*args,**kwargs)
        with patch.object(m.os,'open',side_effect=swap),patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'HOLD_HASH_FILE_UNSAFE'):
                self.do(opener=lambda *a,**k:self.fail('existing verified file must not fetch'))
        self.assertTrue(hit)

    def test_raced_fifo_in_partial_guard_fails_before_network(self):
        """O_NOFOLLOW alone leaves O_RDONLY FIFO opens blocking indefinitely."""
        import os
        part=self.dst/(self.name+'.part')
        part.write_bytes(self.content[:3])
        opened=os.open
        hit=[]
        def swap(path,flags,*args,**kwargs):
            if Path(path)==part and (flags & os.O_ACCMODE)==os.O_RDONLY and not hit:
                self.assertTrue(flags & os.O_NONBLOCK)
                part.unlink();os.mkfifo(part);hit.append(True)
            return opened(path,flags,*args,**kwargs)
        with patch.object(m.os,'open',side_effect=swap),patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'HOLD_PARTIAL_PREIMAGE_CHANGED'):
                self.do(opener=lambda *a,**k:self.fail('no download after guard swap'))
        self.assertTrue(hit)

    def test_raced_fifo_in_partial_append_is_bounded_hold(self):
        """A FIFO swapped during HTTP read may block an O_WRONLY append without O_NONBLOCK."""
        import os
        part=self.dst/(self.name+'.part')
        part.write_bytes(self.content[:3])
        opened=os.open
        hit=[]
        def swap(path,flags,*args,**kwargs):
            if Path(path)==part and (flags & os.O_ACCMODE)==os.O_WRONLY and not hit:
                self.assertTrue(flags & os.O_NONBLOCK)
                part.unlink();os.mkfifo(part);hit.append(True)
            return opened(path,flags,*args,**kwargs)
        with patch.object(m.os,'open',side_effect=swap),patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'HOLD_PARTIAL_APPEND_OPEN_RACE'):
                self.do()
        self.assertTrue(hit)

    def test_raced_fifo_before_partial_fsync_cannot_stall(self):
        """The final fsync open also needs O_NONBLOCK after read/hash verification."""
        import os
        part=self.dst/(self.name+'.part')
        part.write_bytes(self.content)
        opened=os.open
        counts=[]
        def swap(path,flags,*args,**kwargs):
            if Path(path)==part and (flags & os.O_ACCMODE)==os.O_RDONLY:
                counts.append(flags)
                if len(counts)==3:
                    self.assertTrue(flags & os.O_NONBLOCK)
                    part.unlink();os.mkfifo(part)
            return opened(path,flags,*args,**kwargs)
        with patch.object(m.os,'open',side_effect=swap),patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'HOLD_PARTIAL_CHANGED_BEFORE_FSYNC'):
                self.do(opener=lambda *a,**k:self.fail('complete partial never fetches'))
        self.assertEqual(len(counts),3)


    def test_download_lock_inode_swap_during_http_holds_before_append(self):
        """A second owner must not acquire a newly-created lock while the first appends."""
        lock_path=self.dst/'.nox-deepseek-owner.lock'
        def swapped_opener(req, timeout=30):
            self.assertTrue(lock_path.is_file())
            lock_path.unlink()  # Original flock remains held on now-unlinked inode.
            lock_path.write_bytes(b'SECOND-WORKER-LOCK')
            return self.opener(req, timeout=timeout)
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold, 'HOLD_DOWNLOAD_LOCK_REPLACED'):
                self.do(opener=swapped_opener)
        self.assertEqual(lock_path.read_bytes(),b'SECOND-WORKER-LOCK')
        part=self.dst/(self.name+'.part')
        self.assertEqual(part.stat().st_size if part.exists() else 0,0)
        self.assertFalse((self.dst/self.name).exists())

    def test_download_lock_rejects_insecure_existing_permissions(self):
        """The existing owner lock must not be writable by another Unix identity."""
        lock_path=self.dst/'.nox-deepseek-owner.lock'
        lock_path.write_bytes(b'EXISTING')
        lock_path.chmod(0o666)
        with patch.object(m,'RESERVE',0):
            with self.assertRaisesRegex(m.Hold,'HOLD_DOWNLOAD_LOCK_PERMISSIONS'):
                self.do(opener=lambda *args, **kwargs: self.fail('network must not start'))
        self.assertEqual(lock_path.read_bytes(),b'EXISTING')
        self.assertFalse((self.dst/(self.name+'.part')).exists())

    def test_short_disk_write_drains_exact_bytes_before_receipt(self):
        # Unbuffered regular-file write is permitted to return a short count.
        class ShortSink:
            def __init__(self):
                self.data = bytearray()
                self.calls = 0
            def write(self, data):
                self.calls += 1
                count = max(1, len(data) // 2)
                self.data.extend(data[:count])
                return count
        sink = ShortSink()
        with patch.object(m, 'stop') as stop, patch.object(m, 'lease') as lease:
            count = m._write_checked(sink, b'abcdefgh', self.root, self.lease, self.request)
        self.assertEqual(count, 8)
        self.assertEqual(bytes(sink.data), b'abcdefgh')
        self.assertGreater(sink.calls, 1)
        self.assertEqual(stop.call_count, sink.calls)
        self.assertEqual(lease.call_count, sink.calls)

    def test_zero_progress_disk_write_fails_closed(self):
        class StalledSink:
            def write(self, data):
                return 0
        with patch.object(m, 'stop'), patch.object(m, 'lease'):
            with self.assertRaisesRegex(m.Hold, 'HOLD_PARTIAL_WRITE_NO_PROGRESS'):
                m._write_checked(StalledSink(), b'data', self.root, self.lease, self.request)

    def test_stop_between_short_writes_keeps_partial_and_holds(self):
        class OneByteSink:
            def __init__(self):
                self.data = bytearray()
            def write(self, data):
                self.data.extend(data[:1])
                return 1
        sink = OneByteSink()
        checks = {'count': 0}
        def owner_stop(root):
            checks['count'] += 1
            if checks['count'] == 2:
                raise m.Hold('OWNER_STOP')
        with patch.object(m, 'stop', side_effect=owner_stop), patch.object(m, 'lease'):
            with self.assertRaisesRegex(m.Hold, 'OWNER_STOP'):
                m._write_checked(sink, b'abc', self.root, self.lease, self.request)
        self.assertEqual(bytes(sink.data), b'a')


    def test_short_write_rechecks_original_lock_before_every_continuation(self):
        """A replaced owner lock must stop additional bytes on short writes."""
        class OneByteSink:
            def __init__(self):
                self.data=bytearray()
            def write(self,view):
                self.data.extend(view[:1])
                return 1
        sink=OneByteSink()
        checks={'count':0}
        def owner_lock_guard():
            checks['count']+=1
            if checks['count']==3:
                raise m.Hold('HOLD_DOWNLOAD_LOCK_REPLACED')
        with patch.object(m,'stop'),patch.object(m,'lease'):
            with self.assertRaisesRegex(m.Hold,'HOLD_DOWNLOAD_LOCK_REPLACED'):
                m._write_checked(sink,b'abcd',self.root,self.lease,self.request,owner_lock_guard)
        self.assertEqual(bytes(sink.data),b'ab')
        self.assertEqual(checks['count'],3)

if __name__=='__main__':unittest.main()
