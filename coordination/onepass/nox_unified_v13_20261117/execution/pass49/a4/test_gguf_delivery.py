import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import deliver_gguf_pack as d


def actual_verifier():
    candidates=[Path(__file__).resolve().parents[1]/'role2/verify_deepseek_pack.py',
                Path('/workspace/scratch/98d1e08cfc37/work/role5/final/execution/pass49/role2/verify_deepseek_pack.py')]
    path=next(p for p in candidates if p.is_file())
    spec=importlib.util.spec_from_file_location('fixture_actual_verifier',path)
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);return v


class Response(io.BytesIO):
    def __init__(self,data,start,end,total):
        super().__init__(data);self.status=206
        self.headers={'Content-Range':f'bytes {start}-{end}/{total}','Content-Length':str(end-start+1)}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.stage=self.root/'stage';self.stage.mkdir(mode=0o700)
        self.v=actual_verifier();self.payloads={f'fixture-{i}.gguf':b'GGUF'+bytes([i])*9 for i in range(5)}
        self.payloads['fixture-Engram-IQ4_NL.gguf']=b'GGUFengram'
        self.git=dict(model='owner/fixture',revision='a'*40,artifacts=[{'name':n,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for n,raw in self.payloads.items()])
        self.drive=dict(schema=self.v.DRIVE_SCHEMA,repository=self.git['model'],revision=self.git['revision'],
            files=[dict(path=r['name'],bytes=r['bytes'],sha256=r['sha256'],url=f"https://huggingface.co/owner/fixture/resolve/{'a'*40}/{r['name']}") for r in self.git['artifacts']],
            total_unique_gguf_bytes=sum(map(len,self.payloads.values())),alias={'path':'fixture-00006-of-00006.gguf','target':'fixture-Engram-IQ4_NL.gguf','duplicate_bytes':False})
        self.calls=[]
    def tearDown(self):self.tmp.cleanup()
    def transport(self,url,start,end):
        name=url.rsplit('/',1)[1];self.calls.append((name,start,end));raw=self.payloads[name]
        return Response(raw[start:end+1],start,end,len(raw))
    def deliver(self,**kwargs):
        return d.deliver(self.stage,self.drive,self.git,byte_budget=kwargs.pop('byte_budget',1000),reserve_bytes=0,verify=self.v,transport=kwargs.pop('transport',self.transport),**kwargs)
    def test_budget_resume_and_atomic_publish_skip_verified(self):
        r=self.deliver(byte_budget=5,publish_to=self.root/'published')
        self.assertEqual(r['transferred_bytes'],5);self.assertFalse(r['published']);self.assertFalse((self.root/'published').exists())
        cursor=json.loads((self.stage/'fixture-0.gguf.cursor.json').read_text());self.assertEqual(cursor['offset'],5)
        r=self.deliver(byte_budget=8);self.assertEqual(r['transferred_bytes'],8)
        self.assertEqual(self.calls[1],('fixture-0.gguf',5,12));self.assertTrue((self.stage/'fixture-0.gguf').is_file())
        self.calls=[];r=self.deliver(publish_to=self.root/'published')
        self.assertTrue(r['complete']);self.assertTrue(r['published']);self.assertFalse(self.stage.exists())
        self.assertFalse(any(n=='fixture-0.gguf' for n,s,e in self.calls))
        for name,raw in self.payloads.items():self.assertEqual((self.root/'published'/name).read_bytes(),raw)
        self.assertEqual(os.readlink(self.root/'published'/self.drive['alias']['path']),self.drive['alias']['target'])
    def test_range_ignored_never_appends(self):
        def bad(url,start,end):r=self.transport(url,start,end);r.status=200;return r
        with self.assertRaisesRegex(RuntimeError,'RANGE_REQUIRED'):self.deliver(transport=bad)
        self.assertEqual((self.stage/'fixture-0.gguf.part').stat().st_size,0)
    def test_bad_content_range_never_appends(self):
        def bad(url,start,end):r=self.transport(url,start,end);r.headers['Content-Range']='bytes 1-5/100';return r
        with self.assertRaisesRegex(RuntimeError,'CONTENT_RANGE'):self.deliver(transport=bad)
        self.assertEqual((self.stage/'fixture-0.gguf.part').stat().st_size,0)
    def test_partial_network_body_retains_resumable_cursor(self):
        def truncated(url,start,end):return Response(self.payloads['fixture-0.gguf'][:3],start,end,13)
        with self.assertRaisesRegex(RuntimeError,'RANGE_TRUNCATED'):self.deliver(byte_budget=8,transport=truncated)
        self.assertEqual(json.loads((self.stage/'fixture-0.gguf.cursor.json').read_text())['offset'],3)
        self.calls=[];r=self.deliver();self.assertTrue(r['complete']);self.assertEqual(self.calls[0][1],3)
    def test_tampered_prefix_is_preserved_and_refused(self):
        self.deliver(byte_budget=5);p=self.stage/'fixture-0.gguf.part';p.write_bytes(b'GGUFx')
        with self.assertRaisesRegex(RuntimeError,'PREFIX_MISMATCH'):self.deliver()
        self.assertEqual(p.read_bytes(),b'GGUFx')
    def test_existing_bad_artifact_never_overwritten(self):
        p=self.stage/'fixture-0.gguf';p.write_bytes(b'keep')
        with self.assertRaisesRegex(RuntimeError,'EXISTING_ARTIFACT'):self.deliver()
        self.assertEqual(p.read_bytes(),b'keep');self.assertEqual(self.calls,[])
    def test_wrong_full_sha_never_published(self):
        def corrupt(url,start,end):r=self.transport(url,start,end);return Response(b'GGUF'+b'x'*(end-start-3),start,end,len(self.payloads[url.rsplit('/',1)[1]]))
        with self.assertRaisesRegex(RuntimeError,'SHA_MISMATCH'):self.deliver(transport=corrupt,publish_to=self.root/'published')
        self.assertFalse((self.root/'published').exists())
    def test_cursor_changed_revision_refused(self):
        self.deliver(byte_budget=5);p=self.stage/'fixture-0.gguf.cursor.json';r=json.loads(p.read_text());r['revision']='b'*40;p.write_text(json.dumps(r))
        with self.assertRaisesRegex(RuntimeError,'CURSOR_IDENTITY'):self.deliver()
    def test_hardlinked_partial_refused(self):
        self.deliver(byte_budget=5);os.link(self.stage/'fixture-0.gguf.part',self.root/'unique')
        with self.assertRaisesRegex(RuntimeError,'NOT_PRIVATE_REGULAR'):self.deliver()
        self.assertEqual((self.root/'unique').stat().st_size,5)
    def test_publish_destination_race_not_replaced(self):
        target=self.root/'race';target.mkdir();(target/'unique').write_bytes(b'keep')
        with self.assertRaises(OSError):d.no_replace(self.stage,target)
        self.assertEqual((target/'unique').read_bytes(),b'keep');self.assertTrue(self.stage.exists())
    def test_fifo_lock_cannot_block_or_be_used(self):
        os.mkfifo(self.stage/'.delivery.lock')
        with self.assertRaisesRegex(RuntimeError,'LOCK_TYPE'):self.deliver()
    def test_storage_reserve_and_link_paths_hold(self):
        with patch.object(d.os,'fstatvfs',return_value=type('FS',(),{'f_bavail':0,'f_frsize':1})()):
            with self.assertRaisesRegex(RuntimeError,'DISK_BUDGET'):self.deliver()
        (self.root/'link').symlink_to(self.stage,target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError,'SYMLINK'):d.plain(self.root/'link')


if __name__=='__main__':unittest.main()
