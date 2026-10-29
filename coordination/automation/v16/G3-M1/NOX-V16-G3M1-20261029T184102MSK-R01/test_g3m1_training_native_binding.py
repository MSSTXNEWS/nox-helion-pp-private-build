"""G3/M1 source-only synthetic contract tests: NEVER start a real GPU worker."""
import importlib.util
import pathlib
import threading
import unittest

PATH = pathlib.Path(__file__).with_name("p04_training_native_binding_g3m1.py")
spec = importlib.util.spec_from_file_location("g3m1_native_training", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class G3M1NativeTrainingBindingTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.grants = {"training.start", "training.evaluate"}
        self.attest = True
        self.ready = True
        self.sha = "a" * 64
        def native_action(route):
            def call(session, payload):
                self.calls.append((route, session, dict(payload)))
                return {"route": route, "ownerReceiptSha256": self.sha,
                        "state": "OWNER_ACK_ONLY_NOT_TRAINING_COMPLETE"}
            return call
        self.adapter = mod.ExistingP04TrainingBinding(
            owner_receipt_sha256=self.sha, owner_lease=threading.RLock(),
            native_authorize=lambda session, route: route in self.grants,
            owner_model_and_rights=lambda session, route, sha: self.attest and sha == self.sha,
            existing_backend_ready=lambda: self.ready,
            existing_start=native_action("training.start"),
            existing_evaluate=native_action("training.evaluate"),
            verify_owner_ack=lambda session, route, ack: ack.get("route") == route,
        )

    def test_g3m1_native_start_and_evaluate_owner_callbacks_only(self):
        self.assertEqual(self.adapter.start("native", {"jobId": "x"})["route"], "training.start")
        self.assertEqual(self.adapter.evaluate("native", {"jobId": "x"})["route"], "training.evaluate")
        self.assertEqual([x[0] for x in self.calls], ["training.start", "training.evaluate"])

    def test_g3m1_revoked_scope_rejects_before_owner_call(self):
        self.grants.clear()
        with self.assertRaises(PermissionError):
            self.adapter.start("native", {})
        self.assertEqual(self.calls, [])

    def test_g3m1_missing_model_license_dataset_evidence_fails_closed(self):
        self.attest = False
        with self.assertRaisesRegex(mod.P04NativeTrainingHold, "MODEL_LOCK_HOLD"):
            self.adapter.evaluate("native", {})
        self.assertEqual(self.calls, [])

    def test_g3m1_gpu_unavailable_keeps_owner_action_uninvoked(self):
        self.ready = False
        with self.assertRaisesRegex(mod.P04NativeTrainingHold, "WORKER_UNAVAILABLE"):
            self.adapter.start("native", {})
        self.assertEqual(self.calls, [])

    def test_g3m1_bad_wire_rejected_before_side_effect(self):
        for payload in ({"bad": float("nan")}, {"bad": "\ud800"}, []):
            with self.subTest(payload=repr(payload)):
                with self.assertRaises(mod.P04NativeTrainingHold):
                    self.adapter.start("native", payload)
        self.assertEqual(self.calls, [])

    def test_g3m1_native_lease_and_revoked_after_owner_call(self):
        def action(session, payload):
            self.grants.remove("training.start")
            return {"route": "training.start", "ownerReceiptSha256": self.sha}
        self.adapter._callbacks["training.start"] = action
        with self.assertRaises(PermissionError):
            self.adapter.start("native", {})

    def test_g3m1_owner_ack_mismatch_fails_closed(self):
        self.adapter._callbacks["training.evaluate"] = lambda *_: {"route":"training.evaluate", "ownerReceiptSha256":"b"*64}
        with self.assertRaisesRegex(mod.P04NativeTrainingHold, "ACK_NOT_VERIFIED"):
            self.adapter.evaluate("native", {})

    def test_g3m1_batch_binds_only_two_owner4_routes(self):
        calls = []
        def existing_binder(dispatcher, owner, provider, methods, *, receipt, probe):
            calls.append((owner, provider, methods, receipt, probe()))
            return frozenset(methods)
        result = self.adapter.register(object(), bind_existing_owner_methods=existing_binder)
        self.assertEqual(result, frozenset({"training.start","training.evaluate"}))
        self.assertEqual(calls[0][0], 4)
        self.assertIs(calls[0][1], self.adapter)
        self.assertEqual(calls[0][3], self.sha)
        self.assertTrue(calls[0][4])

    def test_g3m1_sha_or_native_lease_required(self):
        with self.assertRaises(mod.P04NativeTrainingHold):
            mod.ExistingP04TrainingBinding(owner_receipt_sha256="0"*32,
                owner_lease=threading.RLock(), native_authorize=lambda *_: True,
                owner_model_and_rights=lambda *_: True,
                existing_backend_ready=lambda: True, existing_start=lambda *_: {},
                existing_evaluate=lambda *_: {}, verify_owner_ack=lambda *_: True)


if __name__ == "__main__":
    unittest.main()
