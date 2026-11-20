#!/usr/bin/env python3
"""One focused offline test of NOX's existing native Drive queue integration."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from nox_drive_native_binding import (
    NativeDriveBridge, HANDLER_KIND, capability_descriptor, bind_static_native_handlers,
)


class DriveNativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.root=self.base/"private"
        self.root.mkdir(mode=0o700)
        self.ssd=self.base/"cache"
        self.ssd.mkdir(mode=0o700)
        self.st=self.base/"state"
        self.st.mkdir(mode=0o700)
        self.cfg=self.base/"rclone.conf"
        self.cfg.write_text('[noxdrive]\ntype = drive\nroot_folder_id = 1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v\n'
                            'token = {"refresh_token":"TEST-ONLY"}\n')
        self.cfg.chmod(0o600)
        self.owner=True
        self.lease=True
        self.stop=False
        self.chat=False
        self.resource=True
        self.queued=[]
        self.binding={
           "is_owner":lambda who:self.owner and who=="owner",
           "stop_active":lambda:self.stop,
           "lease_current":lambda:self.lease,
           "foreground_active":lambda:self.chat,
           "resource_admission":lambda mode: self.resource and mode=="IO_LIGHT",
           "enqueue":self.enqueue,
        }
        self.app=NativeDriveBridge(self.binding,config=self.cfg,
                                  state=self.st,manifest_root=self.root,ssd=self.ssd)
        self.data=b"safe technical data"
        self.digest=hashlib.sha256(self.data).hexdigest()
        self.task="native-task-01"
        self.m={"schema":"nox.drive.first.v1","task_id":self.task,"action":"ingest",
                "name":"test.gguf","size":len(self.data),"sha256":self.digest,
                "approved":True,"source_url":"https://huggingface.co/owner/weights/resolve/main/test.gguf"}
        self.path,self.sha=self.manifest(self.m)

    def enqueue(self,kind,payload,key):
        self.queued.append((kind,payload,key))
        return {"job_id":"native-receipt-01"}

    def manifest(self,m,name="owner.json"):
        p=self.root/name
        raw=json.dumps(m).encode()
        p.write_bytes(raw);p.chmod(0o600)
        return p,hashlib.sha256(raw).hexdigest()

    def submit(self,**changes):
        a=dict(actor="owner",task_id=self.task,operation="ingest",manifest=str(self.path),
               manifest_sha=self.sha,remote_opt_in=True)
        a.update(changes)
        return self.app.propose(**a)

    def test_descriptor_teaches_approved_operations_not_extra_services(self):
        v=capability_descriptor()
        self.assertIn("ingest",v["operations"])
        self.assertIn("offload",v["operations"])
        self.assertIn("restore_ssd",v["operations"])
        self.assertFalse(v["creates_extra_service_or_gpu_model"])
        self.assertFalse(v["may_delete_original"])

    def test_only_real_owner_enqueues_existing_native_handler(self):
        x=self.submit()
        self.assertEqual(x["state"],"QUEUED_NOT_EXECUTED")
        self.assertEqual(len(self.queued),1)
        self.assertEqual(self.queued[0][0],HANDLER_KIND)
        self.assertEqual(self.queued[0][1]["manifest_sha"],self.sha)
        self.assertEqual(self.queued[0][1]["idempotency_key"],self.queued[0][2])
        self.assertFalse(x["remote_verified"])
        self.assertFalse(x["original_task_accepted"])

    def test_no_remote_or_job_without_google_oauth(self):
        self.cfg.write_text("[noxdrive]\ntype = drive\nroot_folder_id = "
                            "1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v\n")
        self.assertEqual(self.submit()["state"],"HOLD_GOOGLE_OAUTH_REQUIRED")
        self.assertEqual(self.queued,[])

    def test_owner_stop_lease_and_opt_in_are_required(self):
        for params in ({"remote_opt_in":False},{"actor":"stranger"}):
            self.assertEqual(self.submit(**params)["state"],"HOLD_OWNER_AUTH_OR_LEASE")
        self.lease=False
        self.assertEqual(self.submit()["state"],"HOLD_OWNER_AUTH_OR_LEASE")
        self.lease=True;self.stop=True
        self.assertEqual(self.submit()["state"],"HOLD_OWNER_AUTH_OR_LEASE")
        self.assertEqual(self.queued,[])

    def test_exact_manifest_sha_and_root_reject_changes(self):
        self.assertEqual(self.submit(manifest_sha="0"*64)["state"],"HOLD_OWNER_MANIFEST")
        a=self.base/"outside.json";a.write_text(json.dumps(self.m))
        self.assertEqual(self.submit(manifest=str(a))["state"],"HOLD_OWNER_MANIFEST")
        self.assertEqual(self.queued,[])

    def test_fake_result_receipt_does_not_become_done(self):
        self.submit()
        payload=dict(self.queued[0][1])
        with patch("nox_drive_native_binding.drive.execute",
                   return_value={"state":"HOLD","readback_verified":False,"source_deleted":False}):
            self.assertEqual(self.app.worker(payload,cancel=SimpleNamespace(cancelled=False))["state"],
                             "HOLD_NATIVE_DRIVE_EXECUTION")

    def test_approved_worker_invokes_verified_transfer_once(self):
        self.submit()
        payload=dict(self.queued[0][1])
        seen=[]
        with patch("nox_drive_native_binding.drive.execute",
                   side_effect=lambda *args: (
                       seen.append(args),{"state":"VERIFIED_IN_DRIVE",
                       "readback_verified":True,"source_deleted":False})[1]):
            result=self.app.worker(payload,cancel=SimpleNamespace(cancelled=False))
        self.assertEqual(result["state"],"VERIFIED_DRIVE_TRANSFER")
        self.assertTrue(result["remote_verified"])
        self.assertFalse(result["original_task_accepted"])
        self.assertEqual(len(seen),1)

    def test_chat_stop_and_resource_gates_defer_transfer(self):
        self.submit()
        payload=dict(self.queued[0][1])
        for k in ("chat","stop"):
            setattr(self,k,True)
            with patch("nox_drive_native_binding.drive.execute") as call:
                self.assertEqual(self.app.worker(payload,cancel=SimpleNamespace(cancelled=False))["state"],
                                 "DEFERRED_OWNER_OR_CHAT")
                call.assert_not_called()
            setattr(self,k,False)
        self.resource=False
        with patch("nox_drive_native_binding.drive.execute") as call:
            self.assertEqual(self.app.worker(payload,cancel=SimpleNamespace(cancelled=False))["state"],
                             "DEFERRED_OWNER_OR_CHAT")
            call.assert_not_called()
        self.resource=True
        with patch("nox_drive_native_binding.drive.execute") as call:
            self.assertEqual(self.app.worker(payload,cancel=SimpleNamespace(cancelled=True))["state"],
                             "DEFERRED_OWNER_OR_CHAT")
            call.assert_not_called()

    def test_job_payload_drift_refused(self):
        self.submit()
        payload=dict(self.queued[0][1]);payload["operation"]="offload"
        self.assertEqual(self.app.worker(payload,cancel=SimpleNamespace(cancelled=False))["state"],
                         "HOLD_NATIVE_JOB_PIN")

    def test_restore_only_verified_warm_asset_not_ram_or_gpu(self):
        manifest={"schema":"nox.drive.prefetch.v1","remote":"noxchunks:WARM",
                  "assets":[{"name":"test.gguf","size":len(self.data),"sha256":self.digest}]}
        path,sha=self.manifest(manifest,"warm.json")
        queued=self.submit(operation="restore_ssd",manifest=str(path),manifest_sha=sha)
        self.assertEqual(queued["state"],"QUEUED_NOT_EXECUTED")
        seen=[]
        with patch("nox_drive_native_binding.cache.run",
                   side_effect=lambda args:(seen.append(args),
                       {"state":"VERIFIED_STAGE_NOT_LOADED",
                        "assets":[{"asset":"test.gguf","result":"VERIFIED_NEW"}]})[1]):
            result=self.app.worker(self.queued[-1][1],cancel=SimpleNamespace(cancelled=False))
        self.assertEqual(result["state"],"VERIFIED_SSD_STAGE_NOT_GPU_LOADED")
        self.assertEqual(seen[0].mode,"disk")
        self.assertEqual(seen[0].destination,str(self.ssd))


    def test_static_live_registry_needs_verified_owner_and_actual_worker_gates(self):
        callbacks={key:self.binding[key] for key in (
            "stop_active", "lease_current", "foreground_active", "resource_admission")}
        kinds={"owner_order":lambda t:None}
        self.assertEqual(bind_static_native_handlers(
            kinds, callbacks, owner_authorized=lambda:False,
            cancel_for_task=lambda task:SimpleNamespace(cancelled=False)
        )["state"], "HOLD_STATIC_REGISTRY_OWNER")
        self.assertNotIn(HANDLER_KIND, kinds)
        registered=bind_static_native_handlers(
            kinds, callbacks, owner_authorized=lambda:True,
            cancel_for_task=lambda task:SimpleNamespace(cancelled=False))
        self.assertEqual(registered["state"], "STATIC_REGISTRY_BOUND_IN_PROCESS")
        self.assertFalse(registered["native_execution_verified"])
        self.assertIn(HANDLER_KIND, kinds)
        self.assertEqual(bind_static_native_handlers(
            kinds, callbacks, owner_authorized=lambda:True,
            cancel_for_task=lambda task:SimpleNamespace(cancelled=False)
        )["state"], "HOLD_STATIC_REGISTRY_CONFLICT")

        self.submit()
        native={"handler":HANDLER_KIND, "status":"running", "params":dict(self.queued[-1][1])}
        with patch("nox_drive_native_binding.drive.execute",
                   return_value={"state":"VERIFIED_IN_DRIVE",
                                 "readback_verified":True,"source_deleted":False}):
            self.assertEqual(kinds[HANDLER_KIND](native)["state"], "VERIFIED_DRIVE_TRANSFER")
        self.stop=True
        with patch("nox_drive_native_binding.drive.execute") as execute:
            self.assertEqual(kinds[HANDLER_KIND](native)["state"], "DEFERRED_OWNER_OR_CHAT")
            execute.assert_not_called()
        self.stop=False
        self.assertEqual(kinds[HANDLER_KIND]({})["state"], "HOLD_NATIVE_TASK_SHAPE")

    def test_worker_only_bridge_can_never_enqueue_or_approve(self):
        callbacks={key:self.binding[key] for key in (
            "stop_active", "lease_current", "foreground_active", "resource_admission")}
        bridge=NativeDriveBridge(callbacks, config=self.cfg, state=self.st,
                                 manifest_root=self.root, ssd=self.ssd)
        self.assertFalse(bridge.owner_gate("owner"))
        self.assertEqual(bridge.propose(actor="owner",task_id=self.task,
            operation="ingest",manifest=str(self.path),manifest_sha=self.sha,
            remote_opt_in=True)["state"], "HOLD_OWNER_AUTH_OR_LEASE")


    def test_host_registration_requires_owner_and_real_callback(self):
        self.assertEqual(self.app.register_to_existing_dispatcher(None,actor="owner")["state"],
                         "HOLD_NATIVE_REGISTRATION")
        seen=[]
        out=self.app.register_to_existing_dispatcher(
            lambda kind,handler:(seen.append((kind,handler)) or True),actor="owner")
        self.assertEqual(out["state"],"HOST_REGISTRATION_REQUESTED")
        self.assertFalse(out["native_execution_verified"])
        self.assertEqual(seen[0][0],HANDLER_KIND)


if __name__=="__main__":
    unittest.main()
