"""Focused source regression for 0A01 owner STOP admission; no host access."""
import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).with_name("nox_dispatcher_advisor.py")
SPEC = importlib.util.spec_from_file_location("nox_dispatcher_advisor", MODULE_PATH)
advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(advisor)


class StopAdmissionTests(unittest.TestCase):
    def test_missing_stop_fail_closed_before_telemetry(self):
        findings = advisor.assess({"onehost": {"healthy": True}})
        self.assertEqual([x["code"] for x in findings], ["STOP_STATE_UNVERIFIED"])
        self.assertEqual(findings[0]["urgency"], "hold")

    def test_non_boolean_stop_values_fail_closed(self):
        for state in (None, 0, 1, "false", [], {}):
            with self.subTest(state=state):
                findings = advisor.assess({"stop_active": state})
                self.assertEqual([x["code"] for x in findings], ["STOP_STATE_UNVERIFIED"])

    def test_true_stop_remains_safety_stop(self):
        self.assertEqual([x["code"] for x in advisor.assess(
            {"stop_active": True, "trainer": {"ready_for_resume": True}}
        )], ["STOP_ACTIVE"])

    def test_explicit_false_reaches_original_telemetry_contract(self):
        findings = advisor.assess({"stop_active": False})
        self.assertEqual([x["code"] for x in findings], ["TELEMETRY_MISSING"])



class TrainingResumeAttestationTests(unittest.TestCase):
    """0A01: an untrusted ready_for_resume bit cannot authorize training."""

    @staticmethod
    def snapshot():
        return {
            "stop_active": False,
            "onehost": {"healthy": True, "chat_waiting": False,
                        "chat_p95_ms": 180, "chat_budget_ms": 400,
                        "chat_metrics_age_sec": 1},
            "s03": {"readback_verified": True},
            "trainer": {
                "running": False, "ready_for_resume": True,
                "checkpoint_recent": True,
                "checkpoint_readback_verified": True,
                "checkpoint_step": 42,
                "resume_cursor_sha256": "a" * 64,
                "checkpoint_resume_cursor_sha256": "a" * 64,
            },
            "gpu": {
                "temperature_sensor_valid": True, "temperature_c": 60,
            },
            "disk": {"free_gib": 30, "checkpoint_reserve_gib": 10},
            "native_queue": {
                "maintenance_busy": False, "active_claims": False,
                "resource_headroom_bytes": 3 * 1024**3,
                "owner_evidence_age_sec": 5,
                "owner_lease_cas_verified": True,
                "immutable_task_source_verified": True,
                "admission_state": "OWNER_REVIEWED",
                "jobs_started": 0,
                "workers": [
                    {"state": "RUNNING", "current_task": None},
                    {"state": "RUNNING", "current_task": None},
                    {"state": "RUNNING", "current_task": None},
                ],
            },
        }

    def test_unattested_json_ready_flag_is_always_hold(self):
        s = self.snapshot()
        findings = advisor.assess(s)
        self.assertIn("TRAIN_RESUME_OWNER_HOLD", [x["code"] for x in findings])
        self.assertNotIn("TRAIN_RESUME_CANDIDATE", [x["code"] for x in findings])

    def test_attested_snapshot_remains_review_only(self):
        s = self.snapshot()
        findings = advisor.assess(s, owner_snapshot_verifier=lambda exact: exact is s)
        target = [x for x in findings if x["code"] == "TRAIN_RESUME_CANDIDATE"]
        self.assertEqual(len(target), 1)
        self.assertEqual(target[0]["urgency"], "review")
        self.assertIn("recheck", target[0]["advice"])

    def test_checkpoint_restore_without_exact_readback_never_gets_review_hint(self):
        for field, value in (
            ("checkpoint_readback_verified", False),
            ("checkpoint_readback_verified", None),
            ("checkpoint_step", None),
            ("checkpoint_step", True),
            ("checkpoint_step", -1),
            ("resume_cursor_sha256", None),
            ("resume_cursor_sha256", "not-a-digest"),
            ("resume_cursor_sha256", "A" * 64),
            ("checkpoint_resume_cursor_sha256", None),
            ("checkpoint_resume_cursor_sha256", "b" * 64),
        ):
            with self.subTest(field=field):
                s = self.snapshot()
                s["trainer"][field] = value
                codes = [x["code"] for x in advisor.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                self.assertIn("TRAIN_RESUME_OWNER_HOLD", codes)
                self.assertNotIn("TRAIN_RESUME_CANDIDATE", codes)

    def test_stale_s03_checkpoint_and_resource_hold(self):
        for path, val in (
            (("s03", "readback_verified"), False),
            (("trainer", "checkpoint_recent"), None),
            (("gpu", "temperature_c"), 70),
            (("gpu", "temperature_sensor_valid"), False),
            (("disk", "free_gib"), float("nan")),
            (("native_queue", "active_claims"), True),
            (("native_queue", "resource_headroom_bytes"), 29000000),
            (("native_queue", "maintenance_busy"), None),
            (("native_queue", "owner_evidence_age_sec"), None),
            (("native_queue", "owner_evidence_age_sec"), 31),
            (("native_queue", "owner_evidence_age_sec"), -1),
            (("native_queue", "owner_evidence_age_sec"), True),
            (("native_queue", "owner_lease_cas_verified"), False),
            (("native_queue", "owner_lease_cas_verified"), None),
        ):
            with self.subTest(path=path, val=val):
                s = self.snapshot()
                s[path[0]][path[1]] = val
                codes = [x["code"] for x in advisor.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                self.assertIn("TRAIN_RESUME_OWNER_HOLD", codes)
                self.assertNotIn("TRAIN_RESUME_CANDIDATE", codes)

    def test_attested_partial_queue_never_advertises_training_resume(self):
        # Exact owner signature alone does not fill missing queue/workers,
        # immutable source or admission state. The baseline is complete.
        for field in ("workers", "admission_state", "jobs_started",
                      "immutable_task_source_verified"):
            with self.subTest(field=field):
                s = self.snapshot()
                s["native_queue"].pop(field)
                codes = [x["code"] for x in advisor.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                self.assertIn("TRAIN_RESUME_OWNER_HOLD", codes)
                self.assertNotIn("TRAIN_RESUME_CANDIDATE", codes)
        for field, val in (("workers", []), ("jobs_started", True),
                           ("immutable_task_source_verified", False)):
            with self.subTest(field=field):
                s = self.snapshot()
                s["native_queue"][field] = val
                codes = [x["code"] for x in advisor.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                self.assertIn("TRAIN_RESUME_OWNER_HOLD", codes)
                self.assertNotIn("TRAIN_RESUME_CANDIDATE", codes)

    def test_busy_worker_cursor_overrides_cached_no_claims_for_resume(self):
        s = self.snapshot()
        s["native_queue"]["workers"][0]["current_task"] = "6A02"
        observed = [x["code"] for x in advisor.assess(
            s, owner_snapshot_verifier=lambda exact: exact is s)]
        self.assertIn("TRAIN_RESUME_OWNER_HOLD", observed)
        self.assertNotIn("TRAIN_RESUME_CANDIDATE", observed)

    def test_chat_precedence_and_fresh_latency_gate_resume(self):
        # A cached ready_for_resume must never compete with a waiting
        # conversation, unverified chat status or exhausted latency budget.
        cases = (
            ("chat_waiting", True),
            ("chat_waiting", None),
            ("chat_waiting", "false"),
            ("chat_p95_ms", 400),
            ("chat_p95_ms", 900),
            ("chat_p95_ms", None),
            ("chat_p95_ms", 10**500),
            ("chat_budget_ms", 0),
            ("chat_budget_ms", None),
            ("chat_metrics_age_sec", 31),
            ("chat_metrics_age_sec", None),
        )
        for field, value in cases:
            with self.subTest(field=field, value=str(value)[:20]):
                s = self.snapshot()
                s["onehost"][field] = value
                codes = [x["code"] for x in advisor.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                self.assertIn("TRAIN_RESUME_OWNER_HOLD", codes)
                self.assertNotIn("TRAIN_RESUME_CANDIDATE", codes)

    def test_failed_owner_verifier_is_hold(self):
        s = self.snapshot()
        def broken(_):
            raise RuntimeError("owner verification failed")
        for verifier in (None, lambda _: True if False else 1, broken):
            with self.subTest(verifier=verifier):
                codes = [x["code"] for x in advisor.assess(
                    s, owner_snapshot_verifier=verifier)]
                self.assertIn("TRAIN_RESUME_OWNER_HOLD", codes)

if __name__ == "__main__":
    unittest.main()
