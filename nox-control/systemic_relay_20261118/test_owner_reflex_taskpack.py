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

    def test_forged_authority_is_rejected(self):
        m, o, p = fixture()
        o["staged_research_candidates"][0]["authority"] = "OWNER_REVIEWED"
        with self.assertRaisesRegex(ValueError, "HOLD_REFLEX_AUTHORITY"):
            module.propose_successor(m, o, p)


if __name__ == "__main__":
    unittest.main()
