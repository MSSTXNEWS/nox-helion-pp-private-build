import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from nox_integrations import Config,DriveAdapter,IntegrationBridge,BridgeError
from nox_integrations.core import BoundedRunner,HTTPSJSON
from nox_integrations.providers import Providers


class DriveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.store=self.root/"fake_remote";self.store.mkdir()
        (self.store/"NOX").mkdir()
        self.artifacts=self.root/"artifacts";self.artifacts.mkdir()
        self.cache=self.root/"cache";self.cache.mkdir()
        self.bin=self.root/"rclone fixture"
        code=Path(__file__).with_name("fake_rclone.py").read_text().split("\n",1)[1]
        self.bin.write_text("#!"+sys.executable+"\n"+code);self.bin.chmod(0o700)
        self.rc=self.root/"rclone.conf"
        self.rc.write_text(json.dumps({"fixture_store":str(self.store)}));self.rc.chmod(0o600)
        self.cfg=Config({"NOX_DRIVE_REMOTE":"test","NOX_DRIVE_ROOT":"NOX","NOX_RCLONE_BIN":str(self.bin),
                         "NOX_RCLONE_CONFIG":str(self.rc),"NOX_ARTIFACT_ROOT":str(self.artifacts),
                         "NOX_DRIVE_CACHE_ROOT":str(self.cache),"NOX_CACHE_HEADROOM_BYTES":"1",
                         "NOX_ALLOW_DISK_CACHE":"1",
                         "NOX_NOTION_TOKEN":"fixture-secret-never-export"})
        self.drive=DriveAdapter(self.cfg)
    def tearDown(self):
        self.tmp.cleanup()
    def seed(self,name,data):
        p=self.store/"NOX"/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def test_check_list_read_and_literal_shell_characters(self):
        name="hello;$(not-executed).md";digest=self.seed(name,"Привет NOX".encode())
        self.assertTrue(self.drive.check()["project_root_accessible"])
        self.assertEqual(self.drive.list(limit=1)["items"][0]["path"],name)
        self.assertEqual(self.drive.read(name)["sha256"],digest)
        self.assertEqual(self.drive.read(name)["content"],"Привет NOX")

    def test_traversal_and_remote_override_rejected(self):
        for p in ("../outside","/etc/passwd","a/../b","remote:secret","a\\b","a//b","a\x00b"):
            with self.subTest(path=p),self.assertRaises(BridgeError):
                self.drive.read(p)

    def test_read_rejects_oversized_and_binary(self):
        self.seed("big",b"12345")
        with self.assertRaisesRegex(BridgeError,"DRIVE_READ_TYPE_OR_SIZE"):
            self.drive.read("big",max_bytes=4)
        self.seed("binary",b"\xff\xfe")
        with self.assertRaisesRegex(BridgeError,"REQUIRES_UTF8"):
            self.drive.read("binary")

    def test_download_atomically_publishes_hash_verified_cache(self):
        data=b"weights"*10000;digest=self.seed("models/a.bin",data)
        r=self.drive.download_verified("models/a.bin","chosen/a.bin",digest,len(data))
        self.assertEqual(r["status"],"downloaded_verified")
        self.assertEqual(Path(r["local_path"]).read_bytes(),data)
        self.assertEqual(list(self.cache.rglob("*.part")),[])
        self.assertEqual(self.drive.download_verified("models/a.bin","chosen/a.bin",digest,len(data))["status"],"cache_hit_verified")

    def test_download_wrong_sha_cleans_part_and_never_publishes(self):
        self.seed("m",b"abc")
        with self.assertRaisesRegex(BridgeError,"SHA_MISMATCH"):
            self.drive.download_verified("m","bad.bin","0"*64,3)
        self.assertFalse((self.cache/"bad.bin").exists())
        self.assertEqual(list(self.cache.rglob("*.part")),[])

    def test_download_conflict_keeps_existing_and_symlink_is_rejected(self):
        digest=self.seed("m",b"abc")
        (self.cache/"kept").write_bytes(b"old")
        with self.assertRaisesRegex(BridgeError,"CONFLICT"):
            self.drive.download_verified("m","kept",digest,3)
        self.assertEqual((self.cache/"kept").read_bytes(),b"old")
        (self.cache/"linked").symlink_to(self.artifacts,target_is_directory=True)
        with self.assertRaises(BridgeError):
            self.drive.download_verified("m","linked/out",digest,3)
        self.assertFalse((self.artifacts/"out").exists())

    def test_size_budget_and_cancel(self):
        digest=self.seed("m",b"abc")
        self.cfg.values.pop("NOX_ALLOW_DISK_CACHE")
        with self.assertRaisesRegex(BridgeError,"DISK_CACHE_REQUIRES_EXPLICIT_OPT_IN"):
            self.drive.download_verified("m","m",digest,3)
        self.cfg.values["NOX_ALLOW_DISK_CACHE"]="1"
        self.cfg.values["NOX_DOWNLOAD_MAX_BYTES"]="2"
        with self.assertRaisesRegex(BridgeError,"INVALID_SIZE"):
            self.drive.download_verified("m","m",digest,3)
        self.cfg.values["NOX_DOWNLOAD_MAX_BYTES"]="100"
        with self.assertRaisesRegex(BridgeError,"CANCELLED"):
            self.drive.download_verified("m","m",digest,3,should_pause=lambda:True)
        self.assertFalse((self.cache/"m").exists())
        self.assertEqual(list(self.cache.rglob("*.part")),[])

    def test_mid_transfer_cancel_removes_part_and_respects_host_stop(self):
        digest=self.seed("m",b"abc")
        real=BoundedRunner()
        class CancelDuringCat:
            def run(inner,argv,**kwargs):
                if argv[1]=="cat":
                    kwargs["sink"].write(b"a")
                    raise BridgeError("CANCELLED")
                return real.run(argv,**kwargs)
        d=DriveAdapter(self.cfg,runner=CancelDuringCat())
        with self.assertRaisesRegex(BridgeError,"CANCELLED"):
            d.download_verified("m","m",digest,3)
        self.assertEqual(list(self.cache.rglob("*.part")),[])
        self.assertFalse((self.cache/"m").exists())
        d=DriveAdapter(self.cfg,should_pause=lambda:True)
        with self.assertRaisesRegex(BridgeError,"CANCELLED"):
            d.download_verified("m","m",digest,3,should_pause=lambda:False)

    def test_publication_race_does_not_replace_other_writer(self):
        digest=self.seed("m",b"abc")
        real=BoundedRunner();destination=self.cache/"m"
        class RacingRunner:
            def run(inner,argv,**kwargs):
                if argv[1]=="cat":
                    destination.write_bytes(b"other-owner-result")
                return real.run(argv,**kwargs)
        with self.assertRaisesRegex(BridgeError,"CONCURRENT_WRITER"):
            DriveAdapter(self.cfg,runner=RacingRunner()).download_verified("m","m",digest,3)
        self.assertEqual(destination.read_bytes(),b"other-owner-result")
        self.assertEqual(list(self.cache.rglob("*.part")),[])

    def test_memfd_verified_sealed_and_owned_reservation_lifetime(self):
        data=b"RAM-model-shard"*2000;digest=self.seed("m",data)
        reserved=[];released=[]
        handle=self.drive.download_memfd_verified("m",digest,len(data),
                    reserve_ram=lambda n:reserved.append(n) or "ram-lease",
                    release_ram=lambda token:released.append(token) or {"released":True},should_pause=lambda:False)
        self.assertEqual(os.read(handle.fileno(),len(data)),data)
        self.assertGreater(reserved[0],len(data))
        self.assertFalse(handle.describe()["model_loaded"])
        with self.assertRaises(OSError):
            os.write(handle.fileno(),b"cannot-mutate")
        fd=handle.fileno();handle.close();handle.close()
        self.assertEqual(released,["ram-lease"])
        with self.assertRaises(OSError):os.fstat(fd)
        self.assertEqual(list(self.cache.iterdir()),[])

    def test_memfd_abort_closes_only_owned_fd_and_releases(self):
        digest=self.seed("m",b"abc")
        real=BoundedRunner();created=[];released=[]
        class AbortRunner:
            def run(inner,argv,**kwargs):
                if argv[1]=="cat":
                    kwargs["sink"].write(b"a")
                    raise BridgeError("CANCELLED")
                return real.run(argv,**kwargs)
        original=os.memfd_create
        def remember(*args,**kwargs):
            fd=original(*args,**kwargs);created.append(fd);return fd
        unrelated=original("unrelated-local-test",os.MFD_CLOEXEC)
        try:
            with patch("os.memfd_create",side_effect=remember),self.assertRaisesRegex(BridgeError,"CANCELLED"):
                DriveAdapter(self.cfg,runner=AbortRunner()).download_memfd_verified("m",digest,3,
                    reserve_ram=lambda n:"lease",release_ram=lambda x:released.append(x) or {"released":True},should_pause=lambda:False)
            self.assertEqual(released,["lease"])
            self.assertEqual(len(created),1)
            with self.assertRaises(OSError):os.fstat(created[0])
            os.fstat(unrelated)
        finally:os.close(unrelated)

    def test_memfd_lost_release_ack_requires_readback_and_never_double_releases(self):
        digest=self.seed("m",b"abc");calls=[]
        lease={"lease_id":"ram-test","fencing_token":7}
        def release(token):
            calls.append(token)
            raise TimeoutError("fixture ACK lost after release")
        handle=self.drive.download_memfd_verified("m",digest,3,
                    reserve_ram=lambda n:lease,release_ram=release,should_pause=lambda:False)
        fd=handle.fileno()
        with self.assertRaisesRegex(BridgeError,"RAM_RELEASE_UNCONFIRMED") as raised:
            handle.close()
        self.assertTrue(raised.exception.outcome_uncertain)
        self.assertTrue(handle.closed)
        self.assertEqual(handle.describe()["lease_release_state"],"UNKNOWN")
        with self.assertRaises(OSError):os.fstat(fd)
        # The number formerly held by this handle may now belong to another file.
        unrelated=os.memfd_create("protected-unrelated-fixture",os.MFD_CLOEXEC)
        try:
            with self.assertRaisesRegex(BridgeError,"RECONCILE_REQUIRED"):handle.close()
            self.assertEqual(len(calls),1);os.fstat(unrelated)
            with self.assertRaisesRegex(BridgeError,"READBACK_UNVERIFIED"):
                handle.reconcile_release({"verified":True,"lease_id":"wrong","fencing_token":7,"released":True})
            handle.reconcile_release({"verified":True,"lease_id":"ram-test","fencing_token":7,"released":True})
            self.assertEqual(handle.close(),{"closed":True,"lease_released":True})
            self.assertEqual(len(calls),1);os.fstat(unrelated)
        finally:os.close(unrelated)

    def test_memfd_missing_ack_cannot_retry_until_host_confirms_still_held(self):
        digest=self.seed("m",b"abc");calls=[]
        def release(token):
            calls.append(token)
            return None if len(calls)==1 else {"released":True}
        handle=self.drive.download_memfd_verified("m",digest,3,
                    reserve_ram=lambda n:"ram-test",release_ram=release,should_pause=lambda:False)
        with self.assertRaisesRegex(BridgeError,"RAM_RELEASE_UNCONFIRMED"):handle.close()
        with self.assertRaisesRegex(BridgeError,"RECONCILE_REQUIRED"):handle.close()
        self.assertEqual(len(calls),1)
        handle.reconcile_release({"verified":True,"lease_id":"ram-test","released":False})
        self.assertTrue(handle.close()["lease_released"])
        self.assertEqual(len(calls),2)

    def test_memfd_abort_with_unknown_release_reports_uncertain_lease(self):
        digest=self.seed("m",b"abc");real=BoundedRunner();created=[]
        class AbortRunner:
            def run(inner,argv,**kwargs):
                if argv[1]=="cat":raise BridgeError("CANCELLED")
                return real.run(argv,**kwargs)
        original=os.memfd_create
        def remember(*args,**kwargs):
            fd=original(*args,**kwargs);created.append(fd);return fd
        with patch("os.memfd_create",side_effect=remember),self.assertRaisesRegex(BridgeError,"RAM_ABORT_RELEASE_UNCONFIRMED") as raised:
            DriveAdapter(self.cfg,runner=AbortRunner()).download_memfd_verified("m",digest,3,
                reserve_ram=lambda n:"lease",release_ram=lambda token:None,should_pause=lambda:False)
        self.assertTrue(raised.exception.outcome_uncertain)
        with self.assertRaises(OSError):os.fstat(created[0])

    def test_upload_has_data_and_manifest_readback_and_is_repeatable(self):
        data=b"verified backup payload";digest=hashlib.sha256(data).hexdigest()
        (self.artifacts/"backup.bin").write_bytes(data)
        r=self.drive.upload_artifact("backup.bin","backups/run.bin",digest)
        self.assertEqual(r["readback_sha256"],digest)
        manifest=json.loads((self.store/"NOX"/r["manifest_path"]).read_text())
        self.assertEqual(manifest["sha256"],digest)
        self.assertEqual(self.drive.upload_artifact("backup.bin","backups/run.bin",digest)["status"],"uploaded_verified")

    def test_upload_conflict_no_overwrite_and_no_secret_stderr(self):
        self.seed("kept",b"original")
        data=b"new";(self.artifacts/"new").write_bytes(data)
        with self.assertRaises(BridgeError) as e:
            self.drive.upload_artifact("new","kept",hashlib.sha256(data).hexdigest())
        self.assertTrue(e.exception.outcome_uncertain)
        self.assertNotIn("DO_NOT_RETURN",str(e.exception))
        self.assertEqual((self.store/"NOX/kept").read_bytes(),b"original")

    def test_upload_secret_and_wrong_hash_never_copy(self):
        data=b"fixture-secret-never-export";(self.artifacts/"secret").write_bytes(data)
        with self.assertRaisesRegex(BridgeError,"SECRET_IN_ARTIFACT"):
            self.drive.upload_artifact("secret","bad",hashlib.sha256(data).hexdigest())
        self.assertFalse((self.store/"NOX/bad").exists())
        (self.artifacts/"ok").write_bytes(b"ok")
        with self.assertRaisesRegex(BridgeError,"SHA_OR_REVISION"):
            self.drive.upload_artifact("ok","bad","0"*64)

    def test_upload_secret_spanning_chunks_is_rejected(self):
        secret=b"fixture-secret-never-export"
        data=b"x"*(1024*1024-5)+secret+b"z"
        (self.artifacts/"boundary").write_bytes(data)
        with self.assertRaisesRegex(BridgeError,"SECRET_IN_ARTIFACT"):
            self.drive.upload_artifact("boundary","bad",hashlib.sha256(data).hexdigest())
        self.assertFalse((self.store/"NOX/bad").exists())


class ConfigAndProcessTests(unittest.TestCase):
    def test_secret_file_requires_0600_and_environment_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"settings.json";p.write_text('{"NOX_GITHUB_TOKEN":"fixture-old"}');p.chmod(0o600)
            c=Config.load({"NOX_INTEGRATIONS_SECRETS_FILE":str(p),"NOX_GITHUB_TOKEN":"fixture-new"})
            self.assertEqual(c.get("NOX_GITHUB_TOKEN"),"fixture-new")
            self.assertNotIn("fixture-new",repr(c))
            p.chmod(0o644)
            with self.assertRaisesRegex(BridgeError,"0600"):
                Config.load({"NOX_INTEGRATIONS_SECRETS_FILE":str(p)})
            p.chmod(0o600);link=Path(td)/"link";link.symlink_to(p)
            with self.assertRaises(BridgeError):
                Config.load({"NOX_INTEGRATIONS_SECRETS_FILE":str(link)})

    def test_process_output_timeout_and_cancel_bounded(self):
        runner=BoundedRunner();env={"PATH":os.defpath}
        with self.assertRaisesRegex(BridgeError,"OUTPUT_LIMIT"):
            runner.run([sys.executable,"-c","print('x'*10000)"],env=env,timeout=2,max_output=100)
        started=time.monotonic()
        with self.assertRaisesRegex(BridgeError,"TIMEOUT"):
            runner.run([sys.executable,"-c","import time;time.sleep(5)"],env=env,timeout=0.15,max_output=100)
        self.assertLess(time.monotonic()-started,2)
        with self.assertRaisesRegex(BridgeError,"CANCELLED"):
            runner.run(["/must/not/start"],env=env,timeout=2,max_output=10,should_pause=lambda:True)

    def test_cli_status_offline_and_missing_credentials(self):
        env={"PATH":os.defpath,"PYTHONPATH":str(Path(__file__).resolve().parents[1])}
        p=subprocess.run([sys.executable,"-m","nox_integrations","status"],env=env,capture_output=True,timeout=5)
        self.assertEqual(p.returncode,0)
        d=json.loads(p.stdout)
        self.assertEqual(len(d["capabilities"]),8)
        self.assertTrue(all(x["status"] in ("pending_credentials","disabled_by_policy") for x in d["capabilities"]))
        self.assertEqual(d["download_policy"]["canonical"],"external_to_verified_drive_to_owned_ram")
        p=subprocess.run([sys.executable,"-m","nox_integrations","proof","notion"],env=env,capture_output=True,timeout=5)
        self.assertEqual(json.loads(p.stdout)["code"],"PENDING_CREDENTIALS")


class FakeResponse:
    def __init__(self,data,status=200,headers=None):
        self.status=status;self.body=io.BytesIO(data);self.headers=headers or {}
    def getheader(self,k):return self.headers.get(k)
    def read1(self,n):return self.body.read(n)
    def close(self):self.body.close()


class CaptureConnection:
    def __init__(self,response,calls):self.response=response;self.calls=calls;self.sock=None
    def request(self,method,path,body,headers):self.calls.append({"method":method,"path":path,"body":body,"headers":headers})
    def getresponse(self):return self.response
    def close(self):pass


class ProviderAndHostTests(unittest.TestCase):
    def config(self):
        return Config({"NOX_NOTION_TOKEN":"notion-fixture-token","NOX_GITHUB_TOKEN":"github-fixture-token",
                       "NOX_GITLAB_TOKEN":"gitlab-fixture-token","NOX_GITHUB_REPO":"owner/project",
                       "NOX_GITLAB_PROJECT":"group/project"})
    def transport(self,data,status=200,headers=None,max_bytes=1048576):
        self.calls=[];self.hosts=[]
        encoded=data if isinstance(data,bytes) else json.dumps(data).encode()
        def factory(host,timeout):
            self.hosts.append(host)
            return CaptureConnection(FakeResponse(encoded,status,headers),self.calls)
        return HTTPSJSON(connection_factory=factory,max_bytes=max_bytes)

    def test_real_provider_request_shapes_and_selected_responses(self):
        t=self.transport({"results":[{"object":"page","id":"p","url":"https://notion.so/p","properties":{"Name":{"type":"title","title":[{"plain_text":"NOX"},{"text":None}]}}}],"has_more":False})
        self.assertEqual(Providers(self.config(),t).notion_search()["pages"][0]["title"],"NOX")
        self.assertEqual(self.hosts,["api.notion.com"])
        self.assertEqual(self.calls[0]["path"],"/v1/search")
        self.assertEqual(self.calls[0]["headers"]["Notion-Version"],"2026-03-11")
        self.assertEqual(json.loads(self.calls[0]["body"])["filter"],{"property":"object","value":"page"})
        t=self.transport({"id":1,"full_name":"owner/project","private":True})
        self.assertTrue(Providers(self.config(),t).github_repo()["private"])
        self.assertEqual(self.calls[0]["path"],"/repos/owner/project")
        t=self.transport({"id":2,"path_with_namespace":"group/project"})
        self.assertEqual(Providers(self.config(),t).gitlab_project()["id"],2)
        self.assertEqual(self.calls[0]["path"],"/api/v4/projects/group%2Fproject")

    def test_redirect_limit_bad_json_and_http_error_never_return_body(self):
        for status,code in ((302,"REDIRECT_REJECTED"),(429,"RATE_LIMITED"),(401,"API_HTTP_ERROR")):
            t=self.transport(b"token=must-not-return",status)
            with self.assertRaisesRegex(BridgeError,code) as e:
                Providers(self.config(),t).github_repo()
            self.assertNotIn("must-not-return",str(e.exception));self.assertEqual(len(self.hosts),1)
        for data,headers,code in ((b"x"*101,{},"API_RESPONSE_LIMIT"),(b"{}",{"Content-Length":"101"},"API_RESPONSE_LIMIT"),(b"not-json",{},"API_INVALID_JSON")):
            t=self.transport(data,headers=headers,max_bytes=100)
            with self.assertRaisesRegex(BridgeError,code):
                Providers(self.config(),t).github_repo()

    def test_no_credentials_no_host_request_and_no_arbitrary_host(self):
        t=self.transport({})
        with self.assertRaisesRegex(BridgeError,"PENDING_CREDENTIALS"):
            Providers(Config({}),t).notion_search()
        self.assertEqual(self.calls,[])
        with self.assertRaisesRegex(BridgeError,"TRANSPORT_NOT_ALLOWED"):
            t.request("attacker.invalid","GET","/",{})
        self.assertEqual(self.hosts,[])

    def test_host_authorization_receipt_and_truthful_state(self):
        t=self.transport({"id":1,"full_name":"owner/project","private":True})
        bridge=IntegrationBridge(self.config(),transport=t)
        before=bridge.registry()
        self.assertEqual(self.calls,[])
        self.assertNotIn("github-fixture-token",json.dumps(before))
        result=bridge.execute("nox.integrations.github.repo.v1",{},task_id="fixture-task")
        self.assertEqual(result["code"],"HOST_BINDING_REQUIRED");self.assertEqual(self.calls,[])
        receipts=[]
        bridge=IntegrationBridge(self.config(),transport=t,authorize=lambda *a:True,
                                 result_sink=lambda r:receipts.append(r) or "fixture-receipt")
        result=bridge.execute("nox.integrations.github.repo.v1",{},task_id="fixture-task")
        self.assertEqual(result["execution_origin"],"local_or_fixture")
        self.assertEqual(len(receipts),1)
        row=next(x for x in bridge.registry()["capabilities"] if ".github." in x["capability"])
        self.assertEqual(row["status"],"ready");self.assertIsNone(row["native_evidence"])

    def test_typed_arguments_secret_rejection_and_persistence_failure(self):
        t=self.transport({"id":1,"full_name":"owner/project"})
        b=IntegrationBridge(self.config(),transport=t,authorize=lambda *a:True,result_sink=lambda r:None)
        r=b.execute("nox.integrations.github.repo.v1",{"shell":"anything"},task_id="t")
        self.assertEqual(r["code"],"UNKNOWN_ARGUMENT");self.assertEqual(self.calls,[])
        r=b.execute("nox.integrations.notion.search.v1",{"query":"notion-fixture-token"},task_id="t")
        self.assertEqual(r["code"],"SECRET_IN_PAYLOAD");self.assertEqual(self.calls,[])
        r=b.execute("nox.integrations.github.repo.v1",{},task_id="t")
        self.assertEqual(r["code"],"RESULT_PERSISTENCE_UNCONFIRMED")
        self.assertFalse(any(x["status"]=="tested_native" for x in b.registry()["capabilities"]))


if __name__=="__main__":unittest.main()
