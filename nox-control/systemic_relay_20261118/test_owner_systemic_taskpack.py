"""Fail-closed source-only tests for REFILL_REQUIRED diagnostics and compilation."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))
import owner_systemic_taskpack as producer
from owner_systemic_refill_eligibility import (
    strict_parent_registry, eligibility_ledger, proposal_predicate_diff,
    special_candidate_gaps,
)
from owner_systemic_refill import acceptance_mapping_valid

PACK = ROOT / "next_pack_44368502183"
SOURCES = ROOT.parent / "four_queue_20261118"
PREVIOUS = ROOT / "mission_pack_v1/package/relay/ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4.json"
REGISTRY = ROOT.parent / "complete_executor_20261118/evidence/all295_execution_disposition.json"


def read(path):
    return producer.read_document(path)


def pinned_inputs():
    docs, raw_sha = {}, {}
    for key,name in (("tasks","work_tasks.json"),("ideas","work_ideas.json"),
                     ("routing_rules","routing_rules.json"),
                     ("routing_overlay","NOX_FOUR_QUEUE_ROUTING_20261118.json")):
        docs[key],raw_sha[key] = read(SOURCES / name)
    docs["receipts"],raw_sha["receipts"] = \
        producer.read_identical_duplicate_document(SOURCES / "work_receipts.json")
    return docs,raw_sha


def exact_registry():
    disposition,_ = read(REGISTRY)
    docs,raw_sha = pinned_inputs()
    return disposition,docs,raw_sha,strict_parent_registry(disposition,docs,raw_sha)


class RefillEligibilityTests(unittest.TestCase):
    def test_reconstructs_exact_295_original_specs_and_acceptance(self):
        disposition,docs,raw_sha,registry = exact_registry()
        self.assertEqual(registry["total_original_ids"],295)
        self.assertEqual(len(registry["parents"]),295)
        self.assertEqual(registry["source_registry_sha256"],disposition["source_registry_sha256"])
        expected = {
            "I-39": ("Q3_TRAINING_WEIGHTS", "MinHash по источникам и отдельный контроль утечки train→holdout"),
            "I-48": ("Q4_INTEGRATION_ACCEPTANCE", "Автогенерация STOP→yield→reconnect→restore локально"),
            "I-50": ("Q4_INTEGRATION_ACCEPTANCE", "Отдельно по языкам и шуму измерить ошибки до и после голосового патча"),
        }
        for task_id,(queue,acceptance) in expected.items():
            parent = registry["parents"][task_id]
            self.assertEqual(parent["queue_id"],queue)
            self.assertEqual(parent["registered_acceptance"],acceptance)
            self.assertEqual(parent["registered_acceptance_sha256"],
                             producer.hashlib.sha256(acceptance.encode()).hexdigest())
            self.assertEqual(parent["required_evidence"],"source")
            self.assertEqual(parent["execution_state"],"UNBOUND_PENDING_REAL_EXECUTION_PLAN")
        self.assertEqual(raw_sha["routing_overlay"],registry["source_registry_sha256"]["routing"])

    def test_source_sha_or_overlay_drift_fails_closed(self):
        disposition,docs,raw_sha,_ = exact_registry()
        wrong = dict(raw_sha)
        wrong["ideas"] = "0" * 64
        with self.assertRaisesRegex(ValueError,"ORIGINAL_SOURCE_SHA_PIN"):
            strict_parent_registry(disposition,docs,wrong)
        changed = copy.deepcopy(disposition)
        row = next(row for row in changed["tasks"] if row["task_id"] == "I-39")
        row["queue_id"] = "Q1_RUNTIME_CHAT"
        with self.assertRaisesRegex(ValueError,"REGISTRY_QUEUE_BINDING"):
            strict_parent_registry(changed,docs,raw_sha)

    def test_receipt_duplicate_projection_is_explicit_and_scope_stable(self):
        _,_,_,registry = exact_registry()
        self.assertTrue(registry["parents"]["2V14-12"]["prior_receipt_projection_ambiguous"])
        self.assertFalse(registry["parents"]["I-39"]["prior_receipt_projection_ambiguous"])
        ledger = {row["task_id"]:row for row in eligibility_ledger(registry)}
        self.assertIn("DUPLICATE_RECEIPT_PROJECTION_REQUIRES_RECONCILIATION",
                      ledger["2V14-12"]["blockers"])

    def test_i39_i48_i50_are_candidate_ids_but_not_executable(self):
        _,_,_,registry = exact_registry()
        census,census_sha = read(PACK / "source_census.json")
        ledger = {row["task_id"]:row for row in eligibility_ledger(registry)}
        gaps = {row["task_id"]:row for row in special_candidate_gaps(registry,census,census_sha)}
        for task_id in ("I-39","I-48","I-50"):
            self.assertTrue(ledger[task_id]["structural_source_candidate"])
            self.assertEqual(ledger[task_id]["state"],"REQUIRES_GROUNDED_REVIEWED_PLAN")
            self.assertIn("EXISTING_IMMUTABLE_VERIFIER_PIN_REQUIRED",
                          ledger[task_id]["required_inputs"])
            self.assertFalse(ledger[task_id]["executable_task_emitted"])
            self.assertFalse(gaps[task_id]["native_job_created"])
            self.assertFalse(gaps[task_id]["original_task_accepted"])
            self.assertFalse(gaps[task_id]["review_or_cas_weakened"])
            self.assertTrue(gaps[task_id]["actionable_missing_fields"])
        self.assertIn("MinHash", gaps["I-39"]["observed_source_evidence"])
        self.assertIn("STOP_YIELD_RECONNECT_RESTORE_SEQUENCE_ACCEPTANCE_REQUIRED",
                      gaps["I-48"]["observed_source_evidence"])
        self.assertIn("no RU/ES noisy-audio corpus",gaps["I-50"]["observed_source_evidence"])
        self.assertEqual(gaps["I-39"]["source_evidence_refs"][0]["sha256"],
                         census["roots"]["NOX_PROJECT_SOURCE"]["forge_split_guard.py"])
        self.assertEqual(gaps["I-50"]["source_evidence_refs"][0]["sha256"],census_sha)
        self.assertEqual(len(gaps["I-50"]["source_evidence_refs"][0]["allowed_paths"]),33)
        self.assertTrue(all(not row["native_job_created"] and not row["original_task_accepted"]
                            for row in gaps.values()))

    def test_acceptance_mapping_requires_full_ordered_coverage_and_pinned_verifier(self):
        acceptance = "MinHash by source; prevent train-to-holdout leakage"
        verifier = "test_forge_split_guard"
        paths = ["forge_split_guard.py", "test_forge_split_guard.py"]
        def mapping(parts):
            return {"registered_acceptance":acceptance,
                "registered_acceptance_sha256":producer.hashlib.sha256(acceptance.encode()).hexdigest(),
                "criteria":[{"id":f"criterion_{index}","acceptance_fragment":part,
                    "verifier_module":verifier,"verifier_anchor":"test_minhash_by_source"}
                    for index,part in enumerate(parts)]}
        self.assertTrue(acceptance_mapping_valid(acceptance,mapping([acceptance]),
            [verifier],paths,["forge_split_guard.py"]))
        self.assertTrue(acceptance_mapping_valid(acceptance,mapping([
            "MinHash by source; ","prevent train-to-holdout leakage"]),
            [verifier],paths,["forge_split_guard.py"]))
        self.assertFalse(acceptance_mapping_valid(acceptance,mapping([
            "MinHash by source"]),[verifier],paths,["forge_split_guard.py"]))
        self.assertFalse(acceptance_mapping_valid(acceptance,mapping([acceptance]),
            [verifier],["forge_split_guard.py"],["forge_split_guard.py"]))
        self.assertFalse(acceptance_mapping_valid(acceptance,mapping([acceptance]),
            [verifier],["forge_split_guard.py"],["forge_split_guard.py","test_forge_split_guard.py"]))

    def test_original_parent_prefixed_queue_entry_blocks_candidate(self):
        _,_,_,registry = exact_registry()
        request = {"original_task_states":[
            {"task_id":"I-39.native4q.training_prerequisites.20261118","status":"pending"}]}
        ledger = {row["task_id"]:row for row in eligibility_ledger(registry,{},request)}
        self.assertFalse(ledger["I-39"]["structural_source_candidate"])
        self.assertIn("PARENT_ALREADY_OBSERVED_IN_REFILL_OUTCOMES",
                      ledger["I-39"]["blockers"])

    def test_current_refill_artifacts_produce_predicate_diff_not_plan(self):
        previous,_ = read(PREVIOUS)
        proposal,_ = read(PACK / "grounded_proposals.json")
        census,_ = read(PACK / "source_census.json")
        request,_ = read(PACK / "refill_request.json")
        _,_,_,registry = exact_registry()
        diff = proposal_predicate_diff(proposal["missions"],registry,census["roots"],request,previous)
        self.assertEqual(len(diff),len(proposal["missions"]))
        self.assertTrue(all(not row["all_passed"] for row in diff))
        by_parent = {row["parent_task_id"]:row for row in diff}
        for task_id in ("0B04","0V14-14","3A01"):
            self.assertIn(task_id,by_parent)
            predicates = {item["predicate"]:item for item in by_parent[task_id]["predicates"]}
            self.assertFalse(predicates["registered_acceptance"]["passed"])
            self.assertFalse(predicates["acceptance_mapping_sha256"]["passed"])
            self.assertFalse(predicates["required_evidence"]["passed"])
        self.assertFalse(any(row["native_publish_performed"] for row in diff))

    def test_stored_refill_request_is_stale_after_original_state_binding_change(self):
        previous,previous_sha = read(PREVIOUS)
        request,_ = read(PACK / "refill_request.json")
        with self.assertRaisesRegex(ValueError,"REFILL_REQUEST_SHAPE"):
            producer._validate_refill_request(request,previous,previous_sha)

    def test_proposal_must_bind_exact_64_hex_refill_request(self):
        proposal,_ = read(PACK / "grounded_proposals.json")
        request,_ = read(PACK / "refill_request.json")
        previous,previous_sha = read(PREVIOUS)
        self.assertTrue(producer._validate_proposal_request(proposal,previous_sha,request))
        changed = copy.deepcopy(proposal)
        changed["request_id"] = "0" * 64
        with self.assertRaisesRegex(ValueError,"PROPOSAL_REFILL_REQUEST_BINDING"):
            producer._validate_proposal_request(changed,previous_sha,request)

    def test_admitted_source_drift_is_explicit_review_candidate_not_replay(self):
        previous,_ = read(PREVIOUS)
        previous["missions"] = [copy.deepcopy(previous["missions"][0])]
        mission = previous["missions"][0]
        mission["mission_id"] = "zip_extract_budget"
        previous_sha = producer.digest(previous)
        input_sha = __import__("owner_systemic_refill")._input(mission)
        task_id = mission["parent_task_id"] + ".relay." + mission["mission_id"] + "." + input_sha[:16]
        task = {"handler":"owner_native_project_work","status":"done",
            "systemic_relay":{"binding":{"mission_id":mission["mission_id"],
                "mission_revision":mission["revision"],"input_sha256":input_sha,
                "root_id":mission["root_id"],"editable_paths":mission["editable_paths"]}}}
        pins = {mission["root_id"]:{row["path"]:row["sha256"] for row in mission["context"]}}
        changed_path = mission["context"][0]["path"]
        pins[mission["root_id"]][changed_path] = "c" * 64
        result = __import__("owner_systemic_refill").select_next(previous,{task_id:task},pins,
            {"slots_available":1,"callback_sha256":"a"*64,"now":1,
             "manifest_sha256":previous_sha})
        self.assertEqual(result["state"],"REFILL_REQUIRED")
        self.assertEqual(result["rows"],[])
        self.assertEqual(len(result["refill_request"]["source_drift_reviews"]),1)
        review = result["refill_request"]["source_drift_reviews"][0]
        self.assertEqual(review["parent_task_id"],mission["parent_task_id"])
        self.assertTrue(review["replay_forbidden"])
        self.assertFalse(review["original_task_accepted"])
        candidate = next(row for row in result["self_monitor"]["staged_research_candidates"]
                         if row.get("mission_id") == "zip_extract_budget")
        self.assertEqual(candidate["mission_revision"],mission["revision"])
        self.assertEqual(candidate["hypothesis"],"REBASE_AGAINST_OBSERVED_SOURCE_DRIFT")
        self.assertFalse(candidate["new_native_job_created"])

    def test_unregistered_acceptance_cannot_be_added_to_old_manifest(self):
        previous,_ = read(PREVIOUS)
        changed = copy.deepcopy(previous)
        mission = changed["missions"][0]
        mission["registered_acceptance"] = "invented test acceptance"
        mission["acceptance_mapping"] = {"registered_acceptance":"invented test acceptance",
            "registered_acceptance_sha256":"0" * 64,"criteria":[]}
        with self.assertRaisesRegex(ValueError,"UNREGISTERED_ACCEPTANCE_MAPPING"):
            producer.validate_manifest(changed)


if __name__ == "__main__":
    unittest.main()
