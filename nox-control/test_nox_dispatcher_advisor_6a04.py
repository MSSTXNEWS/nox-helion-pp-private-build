"""Focused fail-closed 6A04 GPU utilization/admission regression."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).with_name("nox_dispatcher_advisor.py")
spec = importlib.util.spec_from_file_location("nox_dispatcher_advisor", p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def snapshot():
    return {"stop_active": False, "onehost": {"healthy": True, "chat_waiting": False,
                                             "chat_p95_ms": 200, "chat_budget_ms": 300,
                                             "chat_metrics_age_sec": 1},
            "s03": {"readback_verified": True},
            "trainer": {"running": True, "checkpoint_recent": True},
            "gpu": {"temperature_c": 58, "temperature_sensor_valid": True,
                    "utilization_pct": 15, "vram_used_mib": 10000,
                    "vram_total_mib": 16000, "age_sec": 1,
                    "devices": [
                        {"index": 0, "utilization_pct": 15,
                         "vram_used_mib": 5000, "vram_total_mib": 8000},
                        {"index": 1, "utilization_pct": 15,
                         "vram_used_mib": 5000, "vram_total_mib": 8000},
                    ]},
            "cpu_io": {"cpu_busy_pct": 40, "io_wait_pct": 2, "age_sec": 1},
            "disk": {"free_gib": 100},
            "native_queue": {"active_claims": False, "maintenance_busy": False,
                             "resource_headroom_bytes": 3*1024**3,
                             "owner_evidence_age_sec": 2,
                             "owner_lease_cas_verified": True,
                             "immutable_task_source_verified": True,
                             "admission_state": "OWNER_REVIEWED",
                             "jobs_started": 0,
                             "workers": [
                                 {"state": "RUNNING", "current_task": None},
                                 {"state": "RUNNING", "current_task": None},
                                 {"state": "RUNNING", "current_task": None},
                             ]}}


def codes(s):
    return [x["code"] for x in mod.assess(s)]


class GpuSourceEvidenceTests(unittest.TestCase):
    def test_observed_upper_bound_is_not_admission(self):
        s = snapshot()
        result = mod.assess(s, owner_snapshot_verifier=lambda exact: exact is s)
        self.assertEqual([x["code"] for x in result], ["GPU_RESIDUAL_OBSERVED_NOT_ADMITTED"])
        self.assertIn("70", result[0]["advice"])
        self.assertIn("no admission", result[0]["advice"])

    def test_per_gpu_peak_not_pooled_average_controls_spare_hint(self):
        s = snapshot()
        s["gpu"]["utilization_pct"] = 30
        s["gpu"]["devices"][0]["utilization_pct"] = 60
        s["gpu"]["devices"][1]["utilization_pct"] = 0
        result = mod.assess(s, owner_snapshot_verifier=lambda exact: exact is s)
        self.assertEqual([x["code"] for x in result], ["GPU_RESIDUAL_OBSERVED_NOT_ADMITTED"])
        self.assertIn("25", result[0]["advice"])
        self.assertNotIn("55 percentage", result[0]["advice"])

    def test_per_gpu_missing_duplicate_or_saturated_device_fails_closed(self):
        for bad in ("missing", "duplicate", "unmatched_vram", "saturated",
                    "invalid_util", "nonlist"):
            with self.subTest(case=bad):
                s = snapshot()
                if bad == "missing":
                    s["gpu"].pop("devices")
                elif bad == "duplicate":
                    s["gpu"]["devices"][1]["index"] = 0
                elif bad == "unmatched_vram":
                    s["gpu"]["devices"][1]["vram_used_mib"] += 1
                elif bad == "saturated":
                    s["gpu"]["devices"][0]["utilization_pct"] = 95
                elif bad == "invalid_util":
                    s["gpu"]["devices"][0]["utilization_pct"] = float("inf")
                else:
                    s["gpu"]["devices"] = {"index": 0}
                codes_seen = [x["code"] for x in mod.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                expected = ("GPU_RESIDUAL_DEVICE_BUSY_HOLD" if bad == "saturated"
                            else "GPU_RESIDUAL_DEVICE_CENSUS_HOLD")
                self.assertIn(expected, codes_seen)
                self.assertNotIn("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", codes_seen)

    def test_incomplete_native_queue_never_labels_gpu_spare_as_measured(self):
        # Even a snapshot signature and low GPU utilization cannot certify
        # available accelerator resources when lease/worker/source evidence
        # is only a partial JSON dictionary.
        for field in ("workers", "admission_state", "jobs_started",
                      "immutable_task_source_verified"):
            with self.subTest(field=field):
                s = snapshot()
                s["native_queue"].pop(field)
                found = [x["code"] for x in mod.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                self.assertIn("GPU_RESIDUAL_RESOURCE_HOLD", found)
                self.assertNotIn("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", found)

    def test_unattested_owner_flags_cannot_label_spare_gpu_measured(self):
        s = snapshot()
        for verifier in (None, lambda exact: True if False else 1,
                         lambda exact: exact is not s):
            with self.subTest(verifier=verifier):
                found = [x["code"] for x in mod.assess(
                    s, owner_snapshot_verifier=verifier)]
                self.assertIn("GPU_RESIDUAL_SOURCE_UNATTESTED", found)
                self.assertNotIn("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", found)

    def test_missing_host_or_vram_stays_hold(self):
        for field in ("cpu_io",):
            with self.subTest(field=field):
                s=snapshot(); s.pop(field)
                self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])
        s=snapshot(); s["gpu"]["vram_used_mib"]=20000
        self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])

    def test_chat_has_priority(self):
        s=snapshot(); s["onehost"]["chat_waiting"]=True
        self.assertEqual(codes(s), ["CHAT_PRIORITY"])
        s=snapshot(); s["onehost"]["chat_p95_ms"]=400
        self.assertEqual(codes(s), ["GPU_CHAT_PRIORITY"])


    def test_6a03_chat_priority_does_not_yield_without_boundary_proof(self):
        s = snapshot()
        s["onehost"]["chat_waiting"] = True
        issue = [x for x in mod.assess(s) if x["code"] == "CHAT_PRIORITY"][0]
        self.assertEqual(issue["urgency"], "hold")
        self.assertIn("No signal", issue["advice"])

    def test_6a03_safe_boundary_is_owner_review_only(self):
        s = snapshot()
        s["onehost"]["chat_waiting"] = True
        s["trainer"].update(
            yield_boundary="optimizer_step", yield_boundary_complete=True,
            yield_step=42, resume_cursor_sha256="a" * 64,
            checkpoint_step=42, checkpoint_resume_cursor_sha256="a" * 64,
            checkpoint_readback_verified=True,
            yield_owner_lease_cas_verified=True,
        )
        # Unauthenticated JSON flags cannot turn a source suggestion into
        # an actionable training controller command.
        issue = [x for x in mod.assess(s) if x["code"] == "CHAT_PRIORITY"][0]
        self.assertEqual(issue["urgency"], "hold")
        attested = [x for x in mod.assess(
            s, owner_snapshot_verifier=lambda exact: exact is s)
            if x["code"] == "CHAT_PRIORITY"][0]
        self.assertEqual(attested["urgency"], "review")
        self.assertIn("no automatic action", attested["advice"])
        # Either native boundary type is supported only after live owner proof.
        s["trainer"]["yield_boundary"] = "embedding_batch"
        attested = [x for x in mod.assess(
            s, owner_snapshot_verifier=lambda exact: exact is s)
            if x["code"] == "CHAT_PRIORITY"][0]
        self.assertEqual(attested["urgency"], "review")

    def test_6a03_invalid_or_stale_cursor_and_owner_evidence_hold(self):
        for scope, field, value in (
            ("trainer", "yield_boundary", "unsafe_mid_step"),
            ("trainer", "yield_boundary_complete", False),
            ("trainer", "yield_step", True),
            ("trainer", "resume_cursor_sha256", "broken"),
            ("trainer", "checkpoint_step", 41),
            ("trainer", "checkpoint_step", True),
            ("trainer", "checkpoint_step", None),
            ("trainer", "checkpoint_resume_cursor_sha256", "b" * 64),
            ("trainer", "checkpoint_resume_cursor_sha256", None),
            ("trainer", "checkpoint_readback_verified", None),
            ("trainer", "yield_owner_lease_cas_verified", False),
            ("native_queue", "maintenance_busy", True),
            ("native_queue", "owner_lease_cas_verified", False),
            ("native_queue", "owner_evidence_age_sec", 31),
        ):
            with self.subTest(field=field):
                s = snapshot()
                s["onehost"]["chat_waiting"] = True
                s["trainer"].update(
                    yield_boundary="optimizer_step", yield_boundary_complete=True,
                    yield_step=42, resume_cursor_sha256="a" * 64,
                    checkpoint_step=42, checkpoint_resume_cursor_sha256="a" * 64,
                    checkpoint_readback_verified=True,
                    yield_owner_lease_cas_verified=True,
                )
                s[scope][field] = value
                target = [x for x in mod.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)
                    if x["code"] == "CHAT_PRIORITY"][0]
                self.assertEqual(target["urgency"], "hold")
        s = snapshot()
        s["stop_active"] = True
        s["onehost"]["chat_waiting"] = True
        self.assertEqual([x["code"] for x in mod.assess(s)], ["STOP_ACTIVE"])

    def test_6a03_checkpoint_and_boundary_must_share_exact_step_cursor(self):
        s = snapshot()
        s["onehost"]["chat_waiting"] = True
        s["trainer"].update(
            yield_boundary="embedding_batch", yield_boundary_complete=True,
            yield_step=118, resume_cursor_sha256="c" * 64,
            checkpoint_step=117, checkpoint_resume_cursor_sha256="c" * 64,
            checkpoint_readback_verified=True, yield_owner_lease_cas_verified=True,
        )
        verify = lambda exact: exact is s
        for step, checkpoint_cursor in ((117, "c" * 64),
                                        (118, "d" * 64),
                                        (True, "c" * 64)):
            with self.subTest(step=step, checkpoint_cursor=checkpoint_cursor[:4]):
                s["trainer"]["checkpoint_step"] = step
                s["trainer"]["checkpoint_resume_cursor_sha256"] = checkpoint_cursor
                result = [x for x in mod.assess(s, owner_snapshot_verifier=verify)
                          if x["code"] == "CHAT_PRIORITY"][0]
                self.assertEqual(result["urgency"], "hold")
        s["trainer"]["checkpoint_step"] = 118
        s["trainer"]["checkpoint_resume_cursor_sha256"] = "c" * 64
        result = [x for x in mod.assess(s, owner_snapshot_verifier=verify)
                  if x["code"] == "CHAT_PRIORITY"][0]
        self.assertEqual(result["urgency"], "review")

    def test_cpu_io_pressure_blocks(self):
        s=snapshot(); s["cpu_io"]["io_wait_pct"]=20
        self.assertEqual(codes(s), ["GPU_HOST_PIPELINE_PRESSURE"])

    def test_missing_owner_stop_outranks_budget(self):
        s=snapshot(); s.pop("stop_active")
        self.assertEqual(codes(s), ["STOP_STATE_UNVERIFIED"])

    def test_stale_gpu_and_latency_held(self):
        s=snapshot(); s["gpu"]["age_sec"]=40
        self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])
        s=snapshot(); s["onehost"]["chat_metrics_age_sec"]=40
        self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])

    def test_missing_or_invalid_utilization_fails_closed(self):
        values=(None, -1, True, "15", 101, float("nan"),
                float("inf"), 10**500)
        for value in values:
            with self.subTest(value=str(value)[:35]):
                s=snapshot(); s["gpu"]["utilization_pct"]=value
                self.assertEqual(codes(s), ["GPU_UTILIZATION_UNVERIFIED"])
        s=snapshot(); s["gpu"].pop("utilization_pct")
        self.assertEqual(codes(s), ["GPU_UTILIZATION_UNVERIFIED"])

    def test_giant_host_and_vram_telemetry_is_a_hold(self):
        # JSON permits arbitrary-size integers; math.isfinite on them raises
        # OverflowError. No malformed metric may crash owner telemetry.
        for section, field in (
                ("gpu", "vram_used_mib"),
                ("gpu", "vram_total_mib"),
                ("gpu", "age_sec"),
                ("cpu_io", "cpu_busy_pct"),
                ("cpu_io", "io_wait_pct"),
                ("cpu_io", "age_sec"),
                ("onehost", "chat_p95_ms"),
                ("onehost", "chat_budget_ms"),
                ("onehost", "chat_metrics_age_sec")):
            with self.subTest(section=section, field=field):
                s = snapshot()
                s[section][field] = 10**500
                self.assertEqual(codes(s), ["GPU_RESIDUAL_UNVERIFIED"])

    def test_low_utilization_with_invalid_thermal_evidence_is_hold(self):
        for metric, value in (("temperature_sensor_valid", False),
                              ("temperature_sensor_valid", None),
                              ("temperature_c", 70),
                              ("temperature_c", 99),
                              ("temperature_c", float("nan")),
                              ("temperature_c", None)):
            with self.subTest(metric=metric, value=value):
                s = snapshot()
                s["gpu"][metric] = value
                current = codes(s)
                self.assertIn("GPU_RESIDUAL_THERMAL_HOLD", current)
                self.assertNotIn("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", current)

    def test_degraded_serving_or_s03_never_claims_spare_gpu(self):
        for section, field in (("onehost", "healthy"),
                               ("s03", "readback_verified")):
            with self.subTest(section=section):
                s = snapshot()
                s[section][field] = False
                current = codes(s)
                self.assertIn("GPU_RESIDUAL_SERVICE_HOLD", current)
                self.assertNotIn("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", current)
                self.assertIn("ONEHOST_DEGRADED" if section == "onehost"
                              else "S03_NOT_VERIFIED", current)

    def test_existing_owner_claim_or_maintenance_blocks_gpu_slack_hint(self):
        # A low-utilization instant is not spare capacity during an active
        # owner native claim or an owner maintenance window.
        for field in ("active_claims", "maintenance_busy"):
            with self.subTest(field=field):
                s = snapshot()
                s["native_queue"] = {"active_claims": False,
                                     "maintenance_busy": False}
                s["native_queue"][field] = True
                current = codes(s)
                self.assertIn("GPU_RESIDUAL_OWNER_BUSY_HOLD", current)
                self.assertNotIn("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", current)

    def test_unknown_owner_claim_state_never_suggests_spare_gpu(self):
        # An otherwise healthy low-utilization snapshot without owner claim
        # provenance is not proof that an independent GPU task can start.
        baseline = snapshot()
        baseline.pop("native_queue")
        self.assertIn("GPU_RESIDUAL_OWNER_UNVERIFIED", codes(baseline))
        for field, value in (("active_claims", None),
                             ("active_claims", 0),
                             ("active_claims", 1),
                             ("active_claims", "false"),
                             ("maintenance_busy", None),
                             ("maintenance_busy", 0),
                             ("maintenance_busy", "false")):
            with self.subTest(field=field, value=value):
                s = snapshot()
                s["native_queue"][field] = value
                observed = codes(s)
                self.assertIn("GPU_RESIDUAL_OWNER_UNVERIFIED", observed)
                self.assertNotIn("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", observed)

    def test_low_gpu_utilization_does_not_override_cgroup_or_owner_gates(self):
        # 6A04: even owner-attested low utilization must not contradict
        # native RAM pressure or stale/missing owner authorization.
        for field, value in (
            ("resource_headroom_bytes", None),
            ("resource_headroom_bytes", 0),
            ("resource_headroom_bytes", 2 * 1024**3 - 1),
            ("resource_headroom_bytes", True),
            ("owner_evidence_age_sec", None),
            ("owner_evidence_age_sec", 31),
            ("owner_evidence_age_sec", True),
            ("owner_lease_cas_verified", False),
            ("owner_lease_cas_verified", None),
        ):
            with self.subTest(field=field, value=value):
                s = snapshot()
                s["native_queue"][field] = value
                observed = [x["code"] for x in mod.assess(
                    s, owner_snapshot_verifier=lambda exact: exact is s)]
                self.assertIn("GPU_RESIDUAL_RESOURCE_HOLD", observed)
                self.assertNotIn("GPU_RESIDUAL_OBSERVED_NOT_ADMITTED", observed)

    def test_high_valid_utilization_is_not_admission(self):
        s=snapshot(); s["gpu"]["utilization_pct"]=100
        # A quiet/high-utilization GPU does not prove a live owner lease.
        # This fixture deliberately lacks the fresh 6A02 owner attestation.
        self.assertEqual(codes(s), ["NATIVE_QUEUE_UNVERIFIED"])


if __name__ == "__main__":
    unittest.main()
