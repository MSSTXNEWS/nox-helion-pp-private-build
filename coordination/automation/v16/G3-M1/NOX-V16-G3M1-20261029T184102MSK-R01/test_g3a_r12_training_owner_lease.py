"""G3-A R12: isolate real source owner lease without starting training/GPU."""
import importlib.util
import pathlib
import threading
import unittest

SRC = pathlib.Path(__file__).with_name("p04_training_native_binding_g3m1.py")
spec = importlib.util.spec_from_file_location("g3a_r12_training_binding", SRC)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExplicitlyDeniedOwnerLease:
    def __init__(self):
        self.entered = 0
        self.exited = 0

    def __enter__(self):
        self.entered += 1
        return False

    def __exit__(self, exc_type, exc, tb):
        self.exited += 1
        return False


class SuccessfulNoneLease:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class G3AR12OwnerLeaseFailClosed(unittest.TestCase):
    def binding(self, lease):
        called = []
        sha = "a" * 64

        def authorize(*args):
            called.append("authorize")
            return True

        def attest(*args):
            called.append("attest")
            return True

        def ready():
            called.append("ready")
            return True

        def native_action(session, payload):
            called.append("native_action")
            return {"route": payload["route"], "ownerReceiptSha256": sha}

        def start(session, payload):
            called.append("training.start")
            return {"route": "training.start", "ownerReceiptSha256": sha}

        def evaluate(session, payload):
            called.append("training.evaluate")
            return {"route": "training.evaluate", "ownerReceiptSha256": sha}

        owner = module.ExistingP04TrainingBinding(
            owner_receipt_sha256=sha, owner_lease=lease,
            native_authorize=authorize,
            owner_model_and_rights=attest, existing_backend_ready=ready,
            existing_start=start, existing_evaluate=evaluate,
            verify_owner_ack=lambda *_: True,
        )
        return owner, called

    def test_g3a_r12_denied_start_cannot_reach_authorize_or_training(self):
        lease = ExplicitlyDeniedOwnerLease()
        owner, called = self.binding(lease)
        with self.assertRaisesRegex(module.P04NativeTrainingHold,
                                    "P04_NATIVE_OWNER_LEASE_DENIED"):
            owner.start("native-session", {"requestId": "approved"})
        self.assertEqual(called, [])
        self.assertEqual((lease.entered, lease.exited), (1, 1))

    def test_g3a_r12_denied_evaluate_cannot_reach_owner(self):
        owner, called = self.binding(ExplicitlyDeniedOwnerLease())
        with self.assertRaisesRegex(module.P04NativeTrainingHold,
                                    "P04_NATIVE_OWNER_LEASE_DENIED"):
            owner.evaluate("native-session", {"checkpoint": "owned"})
        self.assertEqual(called, [])

    def test_g3a_r12_standard_reentrant_lock_is_supported(self):
        owner, called = self.binding(threading.RLock())
        ack = owner.start("native-session", {"requestId": "approved"})
        self.assertEqual(ack["route"], "training.start")
        self.assertIn("training.start", called)

    def test_g3a_r12_context_manager_yielding_none_remains_supported(self):
        owner, called = self.binding(SuccessfulNoneLease())
        ack = owner.evaluate("native-session", {"checkpoint": "owned"})
        self.assertEqual(ack["route"], "training.evaluate")
        self.assertIn("training.evaluate", called)


if __name__ == "__main__":
    unittest.main()
