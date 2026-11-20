#!/usr/bin/env python3
"""Focused offline contract: no local downloads, SHA pinned, no eviction."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location("nox_drive_first",Path(__file__).with_name("nox_drive_first.py"))
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)


class Response(io.BytesIO):
    status=200
    headers={}
    def __init__(self, raw, url, length=None):
        super().__init__(raw)
        self.url=url
        self.headers={} if length is None else {"Content-Length":str(length)}
    def geturl(self):
        return self.url


class FakeChild:
    def __init__(self, data=b""):
        self.stdin=io.BytesIO()
        self.stdout=io.BytesIO(data)
        self.returncode=0
    def poll(self):
        return self.returncode
    def wait(self, timeout=None):
        return self.returncode
    def terminate(self):
        self.returncode=-15
    def kill(self):
        self.returncode=-9


class DriveFirstTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.conf=self.root/"rclone.conf"
        self.state=self.root/"state"
        self.state.mkdir(mode=0o700)
        self.data=b"NOX verified sample weight content."
        self.digest=hashlib.sha256(self.data).hexdigest()
        self.asset={"schema":m.SCHEMA,"task_id":"task-001","action":"ingest",
                    "name":"test.gguf","size":len(self.data),"sha256":self.digest,
                    "approved":True,"source_url":"https://huggingface.co/model/resolve/main/test.gguf"}

    def manifest(self,doc=None):
        p=self.root/"owner-manifest.json"
        raw=json.dumps(doc or self.asset).encode()
        p.write_bytes(raw)
        p.chmod(0o600)
        return p,hashlib.sha256(raw).hexdigest()

    def configure(self,*,remote=m.DEST_ROOT,chunk="1Gi",root=m.ROOT_ID):
        self.conf.write_text("[noxdrive]\ntype = drive\nroot_folder_id = "+root+
            '\ntoken = {"refresh_token":"TEST_ONLY"}\n'+
            "[noxchunks]\ntype = chunker\nremote = "+remote+
            "\nchunk_size = "+chunk+"\nhash_type = md5\n")
        self.conf.chmod(0o600)

    def test_auto_chunker_created_after_google_auth_only(self):
        self.conf.write_text('[noxdrive]\ntype = drive\nroot_folder_id = '+
                             m.ROOT_ID+'\ntoken = {"refresh_token":"TEST_ONLY"}\n')
        self.conf.chmod(0o600)
        called=[]
        def create(args, config, **kw):
            called.append(args)
            with self.conf.open('a') as out:
                out.write('[noxchunks]\ntype = chunker\nremote = '+
                          m.DEST_ROOT+'\nchunk_size = 1Gi\nhash_type = md5\n')
        with patch.object(m,"run_rclone",side_effect=create),patch.object(m,"cgroup_admit"),patch.object(m,"stop_clear"):
            self.assertEqual(m.ensure_chunker(self.conf),self.conf)
        self.assertEqual(called[0][:4],["config","create","noxchunks","chunker"])

    def test_existing_chunker_conflict_never_overwritten(self):
        self.configure(remote="local:/tmp")
        with patch.object(m,"run_rclone") as upload:
            with self.assertRaisesRegex(m.Hold,"CHUNKER_CONFLICT"):
                m.ensure_chunker(self.conf)
            upload.assert_not_called()

    def test_auto_chunker_cannot_bypass_google_auth(self):
        self.conf.write_text('[noxdrive]\ntype = drive\nroot_folder_id = '+
                             m.ROOT_ID+'\n')
        self.conf.chmod(0o600)
        with patch.object(m,"run_rclone") as upload:
            with self.assertRaisesRegex(m.Hold,"GOOGLE_AUTH_REQUIRED"):
                m.ensure_chunker(self.conf)
            upload.assert_not_called()

    def test_manifest_requires_owner_exact_pin(self):
        file,sha=self.manifest()
        self.assertEqual(m.load_manifest(file,sha)["name"],"test.gguf")
        with self.assertRaisesRegex(m.Hold,"MANIFEST_CHANGED"):
            m.load_manifest(file,"a"*64)
        bad=dict(self.asset,approved=False)
        file,sha=self.manifest(bad)
        with self.assertRaisesRegex(m.Hold,"MANIFEST_APPROVAL"):
            m.load_manifest(file,sha)

    def test_url_host_approval_no_redirect_to_private_host(self):
        self.assertTrue(m.https_allowed(self.asset["source_url"]))
        for bad in ("http://huggingface.co/a","https://127.0.0.1/x",
                    "https://example.org/model","https://huggingface.co:123/a",
                    "https://user:secret@huggingface.co/a"):
            self.assertFalse(m.https_allowed(bad),bad)
        red=m.VerifiedRedirect()
        with self.assertRaisesRegex(m.Hold,"URL_REDIRECT"):
            red.redirect_request(None,None,302,"redirect",{},"https://localhost/a")

    def test_config_must_have_google_auth_and_exact_chunker_overlay(self):
        with self.assertRaisesRegex(m.Hold,"FILE"):
            m.validate_config(self.conf)
        self.configure()
        self.assertEqual(m.validate_config(self.conf),self.conf)
        self.configure(root="WRONG")
        with self.assertRaisesRegex(m.Hold,"GOOGLE_AUTH_REQUIRED"):
            m.validate_config(self.conf)
        self.configure(remote="local:/tmp")
        with self.assertRaisesRegex(m.Hold,"CHUNKER_CONFIG_REQUIRED"):
            m.validate_config(self.conf)

    def test_config_permissions_reject_world_readable_tokens(self):
        self.configure()
        self.conf.chmod(0o644)
        with self.assertRaisesRegex(m.Hold,"FILE_PERMISSIONS"):
            m.validate_config(self.conf)

    def test_low_cgroup_memory_blocks_transfer(self):
        cg=self.root/"cgroup"
        cg.mkdir()
        (cg/"memory.max").write_text(str(8*m.MIB))
        (cg/"memory.current").write_text(str(7*m.MIB))
        with self.assertRaisesRegex(m.Hold,"CGROUP_BUSY"):
            m.cgroup_admit(cg)
        (cg/"memory.max").write_text("max")
        with self.assertRaisesRegex(m.Hold,"CGROUP_UNKNOWN"):
            m.cgroup_admit(cg)

    def test_local_weight_stays_present_after_verified_offload(self):
        weightdir=self.root/"models";weightdir.mkdir()
        weight=weightdir/"test.gguf";weight.write_bytes(self.data)
        x=dict(self.asset,action="offload")
        x.pop("source_url")
        x["source_path"]=str(weight)
        self.configure()
        calls=[]; proofs=[]
        with patch.object(m,"stop_clear"),patch.object(m,"cgroup_admit"),\
             patch.object(m,"safe_local_source",return_value=weight),\
             patch.object(m,"run_rclone",side_effect=lambda args,*a,**kw:calls.append(args)),\
             patch.object(m,"verify_remote",side_effect=lambda *a,**kw:proofs.append((a,kw))):
            result=m.execute(x,self.conf,self.state)
        self.assertEqual(result["state"],"VERIFIED_IN_DRIVE")
        self.assertEqual(result["source_deleted"],False)
        self.assertTrue(weight.is_file())
        self.assertEqual(weight.read_bytes(),self.data)
        self.assertTrue(any("copyto" in cmd for cmd in calls))
        self.assertTrue(any("moveto" in cmd and "--immutable" in cmd for cmd in calls))
        self.assertEqual(len(proofs),2)
        private=json.loads((self.state/"drive-task-001.json").read_text())
        self.assertTrue(private["remote_readback_verified"])

    def test_existing_task_receipt_blocks_replay_before_drive_io(self):
        self.configure()
        receipt=self.state/"drive-task-001.json"
        receipt.write_text("original signed receipt")
        receipt.chmod(0o600)
        with patch.object(m,"stop_clear"),patch.object(m,"cgroup_admit"),\\
             patch.object(m,"run_rclone") as remote:
            with self.assertRaisesRegex(m.Hold,"RECEIPT_ALREADY_EXISTS"):
                m.execute(self.asset,self.conf,self.state)
        remote.assert_not_called()
        self.assertEqual(receipt.read_text(),"original signed receipt")

    def test_receipt_save_is_atomic_create_only(self):
        receipt=self.state/"drive-task-001.json"
        m.save_receipt(receipt,{"original":True})
        before=receipt.read_bytes()
        with self.assertRaisesRegex(m.Hold,"RECEIPT_ALREADY_EXISTS"):
            m.save_receipt(receipt,{"original":False})
        self.assertEqual(receipt.read_bytes(),before)
        self.assertFalse((self.state/".drive-task-001.json.new").exists())

    def test_stream_direct_http_into_rclone_with_exact_size_no_spool(self):
        self.configure()
        target="noxchunks:STAGING/task-001-test.gguf"
        child=FakeChild()
        class Opener:
            def open(self,request,timeout):
                return Response(self.data,self.url,len(self.data))
        opener=Opener()
        opener.data=self.data;opener.url=self.asset["source_url"]
        created=[]
        with patch.object(m.urllib.request,"build_opener",return_value=opener),\
             patch.object(m.subprocess,"Popen",side_effect=lambda cmd,**kw:(created.append(cmd),child)[1]),\
             patch.object(m,"cgroup_admit"),patch.object(m,"stop_clear"):
            m.stream_https(self.asset,target,self.conf)
        self.assertEqual(len(created),1)
        self.assertIn("rcat",created[0])
        self.assertEqual(created[0][created[0].index("--size")+1],str(len(self.data)))
        self.assertNotIn("copyurl",created[0])

    def test_stream_bad_sha_never_returns_success(self):
        child=FakeChild()
        class Opener:
            def open(self,request,timeout):
                return Response(b"BAD",m.SOURCE_HOSTS.__iter__().__next__() and "https://huggingface.co/test",3)
        wrong=dict(self.asset,size=3)
        with patch.object(m.urllib.request,"build_opener",return_value=Opener()),\
             patch.object(m.subprocess,"Popen",return_value=child),\
             patch.object(m,"cgroup_admit"),patch.object(m,"stop_clear"):
            with self.assertRaisesRegex(m.Hold,"SOURCE_SHA"):
                m.stream_https(wrong,"noxchunks:STAGING/test.gguf",self.conf)

    def test_protected_and_symlink_source_rejected(self):
        root=self.root/"models";root.mkdir()
        file=root/"test.gguf";file.write_bytes(self.data)
        self.assertEqual(m.safe_local_source(file,roots=(root,)),file)
        link=root/"linked.gguf";link.symlink_to(file)
        with self.assertRaisesRegex(m.Hold,"SOURCE_FILE"):
            m.safe_local_source(link,roots=(root,))
        with self.assertRaisesRegex(m.Hold,"SOURCE_OUTSIDE_MODELS"):
            m.safe_local_source(file,roots=(self.root/"outside",))
        bad=root/"s03";bad.mkdir()
        b=bad/"secret.gguf";b.write_bytes(b"secret")
        with self.assertRaisesRegex(m.Hold,"SOURCE_PROTECTED"):
            m.safe_local_source(b,roots=(root,))

    def test_no_execute_does_not_contact_google_or_download(self):
        file,sha=self.manifest()
        with patch.object(m,"execute") as action:
            loaded=m.load_manifest(file,sha)
            self.assertEqual(loaded["action"],"ingest")
            action.assert_not_called()


if __name__=="__main__":
    unittest.main()
