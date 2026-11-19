"""Source-only regression tests for proposed Reflex successors."""
import importlib.util
from pathlib import Path
import unittest

target = Path(__file__).parent / "runtime" / "owner_reflex_taskpack.py"
spec = importlib.util.spec_from_file_location("owner_reflex_taskpack", target)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
A, B = "a" * 64, "b" * 64


def fixture(pin=B, hypothesis="REBASE_AGAINST_OBSERVED_SOURCE_DRIFT"):
    manifest = {"schema": "NOX_SYSTEMIC_RELAY_MANIFEST_V1",
                "revision": 2,
                "missions": [{"mission_id": "repair_cache", "revision": 1,
                              "parent_task_id": "3A03", "root_id": "workspace",
                              "context": [{"path": "code/cache.py", "sha256": A}],
                              "editable_paths": ["code/cache.py"]}]}
    monitor = {"schema": "NOX_NATIVE_REFLEX_MONITOR_V1",
               "observation_sha256": A,
               "staged_research_candidates": [{
                   "fingerprint": A, "authority": "RESEARCH_PROPOSAL_ONLY",
                   "hypothesis": hypothesis, "mission_id": "repair_cache",
                   "parent_task_id": "3A03", "root_id": "workspace",
                   "observed_sources": [{"path": "code/cache.py",
                                         "observed_sha256": pin}]}]}
    return manifest, monitor, {"workspace": {"code/cache.py": pin}}


class TaskpackTests(unittest.TestCase):
    def test_changed_source_yields_non_authoritative_revision(self):
        args = fixture()
        result = module.propose_successor(*args)
        self.assertEqual(result["draft_missions"][0]["revision"], 2)
        self.assertEqual(result["draft_missions"][0]["context"][0]["sha256"], B)
        self.assertEqual(result["native_jobs_created"], 0)
        self.assertFalse(result["automatic_owner_approval"])
        self.assertEqual(args[0]["missions"][0]["revision"], 1)

    def test_repeated_snapshot_is_identical(self):
        args = fixture()
        self.assertEqual(module.propose_successor(*args),
                         module.propose_successor(*args))

    def test_stale_observation_cannot_advance(self):
        m, o, p = fixture()
        p["workspace"]["code/cache.py"] = "c" * 64
        result = module.propose_successor(m, o, p)
        self.assertEqual(result["draft_missions"], [])
        self.assertEqual(result["decisions"][0]["state"], "HOLD_OBSERVATION_STALE")

    def test_failure_never_replays_without_investigation(self):
        result = module.propose_successor(*fixture(hypothesis="ANALYZE_FAILED_TERMINAL_RECEIPT"))
        self.assertEqual(result["draft_missions"], [])
        self.assertEqual(result["decisions"][0]["state"], "NEEDS_INVESTIGATION")

    def test_missing_source_is_hold(self):
        m, o, _ = fixture()
        result = module.propose_successor(m, o, {"workspace": {}})
        self.assertEqual(result["draft_missions"], [])
        self.assertEqual(result["decisions"][0]["state"], "HOLD_SOURCE_MISSING")

    def test_unreviewed_manifest_carries_predecessor(self):
        m, o, p = fixture()
        result = module.propose_successor(m, o, p)
        draft = result["draft_manifest"]
        self.assertEqual(draft["review_origin"], "UNREVIEWED_REFLEX_DRAFT")
        self.assertEqual(draft["acceptance_scope"], "DRAFT_ONLY")
        self.assertEqual(draft["revision"], 3)
        self.assertEqual(draft["previous_manifest_sha256"], result["base_manifest_sha256"])
        self.assertEqual(draft["missions"][0]["context"][0]["sha256"], B)

    def test_noneditable_test_change_cannot_be_auto_rebased(self):
        m, o, p = fixture()
        m["missions"][0]["context"].append({"path": "test_cache.py", "sha256": A})
        p["workspace"]["test_cache.py"] = B
        o["staged_research_candidates"][0]["observed_sources"].append(
            {"path": "test_cache.py", "observed_sha256": B})
        result = module.propose_successor(m, o, p)
        self.assertEqual(result["draft_missions"], [])
        self.assertEqual(result["decisions"][0]["state"], "HOLD_UNREVIEWED_CONTEXT_DRIFT")

    def test_owner_review_sha_is_required_and_validated(self):
        import sys
        sys.path.insert(0, str(Path(__file__).parent / "runtime"))
        import owner_systemic_refill as refill
        m, o, p = fixture()
        m.update(
            review_origin="OWNER_REVIEWED",
            acceptance_scope="SOURCE_PATCH_TESTED",
            original_task_accepted=False,
            previous_manifest_sha256=None,
            registry={
                "total_original_ids": 295,
                "source_registry_sha256": {
                    key: A for key in ("tasks", "ideas", "receipts", "routing")},
                "parents": {"3A03": {
                    "spec_sha256": A,
                    "queue_id": "Q1_RUNTIME_CHAT",
                    "required_evidence": "source"}}})
        original = m["missions"][0]
        original.update(
            priority="P1",
            queue_id="Q1_RUNTIME_CHAT",
            repeat_policy="ONCE_PER_REVIEWED_REVISION",
            title="Repair safe cache under a fixed verifier",
            instruction="Fix a documented cache defect in code/cache.py without changing tests.",
            allowed_new_paths=[],
            verification={"kind":"python_unittest", "modules":["test_cache"],
                          "min_tests":1, "timeout_sec":60},
            budget={"lane":"model", "max_model_turns":24, "cpu_seconds":60,
                    "max_searches":0, "max_output_bytes":8192},
            defect={"observed_source_sha256":A, "finding":"Observed invalid cache value",
                    "expected_delta":"Ensure valid cache value",
                    "verification_limit":"Source unittest only"},
        )
        original["context"].append({"path":"test_cache.py", "sha256":A})
        p["workspace"]["test_cache.py"] = A
        o["staged_research_candidates"][0]["observed_sources"].append(
            {"path":"test_cache.py","observed_sha256":A})
        proposal = module.propose_successor(m, o, p)
        with self.assertRaisesRegex(ValueError, "HOLD_REFLEX_REVIEWED_DRAFT_PIN"):
            module.finalize_after_owner_review(proposal, A, refill.validate_manifest)
        reviewed = module.finalize_after_owner_review(
            proposal, proposal["draft_manifest_sha256"], refill.validate_manifest)
        source_pins = {"workspace":p["workspace"]}
        # The source root in real install is NOX_PROJECT_SOURCE. This fixture
        # has a synthetic but correctly validated owner-reviewed root ID.
        admitted = refill.select_next(
            reviewed["manifest"], {}, source_pins,
            {"slots_available":1, "callback_sha256":A, "now":1,
             "manifest_sha256":reviewed["reviewed_manifest_sha256"]})
        self.assertEqual(admitted["state"], "REVIEWED_BATCH_READY")
        self.assertEqual(len(admitted["rows"]),1)
        row = admitted["rows"][0]
        self.assertTrue(refill.validate_binding(
            reviewed["manifest"], admitted["bindings"][row["id"]], row,
            admitted["contracts"][row["params"]["contract_sha256"]]))
        self.assertEqual(admitted["original_acceptance_added"], 0)

    def test_forged_authority_is_rejected(self):
        m, o, p = fixture()
        o["staged_research_candidates"][0]["authority"] = "OWNER_REVIEWED"
        with self.assertRaisesRegex(ValueError, "HOLD_REFLEX_AUTHORITY"):
            module.propose_successor(m, o, p)


if __name__ == "__main__":
    unittest.main()
