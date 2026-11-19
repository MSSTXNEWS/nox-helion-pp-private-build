"""Focused source-only acceptance for the REFILL_REQUIRED taskpack producer."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).parent))
import owner_systemic_taskpack as producer

ROOT = Path(__file__).parent
PACK = ROOT / "next_pack_44368502183"
PREVIOUS = ROOT / "mission_pack_v1/package/relay/ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4.json"
REGISTRY = ROOT.parent / "complete_executor_20261118/evidence/all295_execution_disposition.json"


def read(path):
    return producer.read_document(path)


def canonical_sha(value):
    return hashlib.sha256(producer.canonical(value)).hexdigest()


def fixture():
    previous, previous_sha = read(PREVIOUS)
    proposal, _ = read(PACK / "grounded_proposals.json")
    census, census_sha = read(PACK / "source_census.json")
    refill_request, refill_sha = read(PACK / "refill_request.json")
    disposition, disposition_sha = read(REGISTRY)
    review, _ = read(PACK / "taskpack_review.json")
    refill_request["original_task_states"] = []
    refill_request["original_task_states_sha256"] = producer.digest([])
    refill_request["request_id"] = producer.digest({
        "manifest_sha256": previous_sha,
        "source_pins": refill_request["source_pins"],
        "outcomes": refill_request["outcomes"],
        "original_task_states": []})
    refill_sha = canonical_sha(refill_request)

    # Use only original TaskIDs that remain explicitly unbound in the current
    # disposition. 0V14-14 already has a reviewed plan and is intentionally
    # excluded from this valid successor fixture.
    proposal["missions"] = [m for m in proposal["missions"]
                            if m["parent_task_id"] in {"0B04", "3A01"}]
    proposal["request_id"] = refill_request["request_id"]
    rows = {row["task_id"]: row for row in disposition["tasks"]}
    for mission in proposal["missions"]:
        mission["parent_spec_sha256"] = rows[mission["parent_task_id"]]["spec_sha256"]
    proposal_sha = canonical_sha(proposal)
    review.update(proposal_sha256=proposal_sha,
                  source_census_sha256=census_sha,
                  refill_request_sha256=refill_sha,
                  registry_sha256=disposition_sha,
                  previous_manifest_sha256=previous_sha,
                  reviewed_mission_ids=sorted(m["mission_id"] for m in proposal["missions"]),
                  immutable_verifier_sha256=producer.immutable_verifier_sha256(
                      proposal["missions"], census["roots"]))
    return (previous, previous_sha, proposal, proposal_sha, census, census_sha,
            refill_request, refill_sha, disposition, disposition_sha, review)


def compile_fixture(args):
    return producer.compile_taskpack(*args)


class ReviewedTaskpackTests(unittest.TestCase):
    def test_exact_refill_request_builds_pinned_successor_without_native_write(self):
        args = fixture()
        manifest = compile_fixture(args)
        producer.validate_manifest(manifest)
        self.assertEqual(manifest["registry"], args[0]["registry"])
        self.assertEqual(manifest["previous_manifest_sha256"], args[1])
        self.assertFalse(manifest["original_task_accepted"])
        self.assertEqual(manifest["producer_evidence"]["refill_request_sha256"], args[7])
        self.assertEqual(len(manifest["producer_evidence"]["original_task_spec_pins"]), 2)
        with tempfile.TemporaryDirectory() as temp:
            request = producer.write_package(manifest, temp, previous_sha=args[1])
            self.assertFalse(request["native_write_performed"])
            for gate in ("EXACT_CURRENT_CONFIG_CAS", "EXISTING_NATIVE_OWNER_LEASE",
                         "ALL_OLD_TASKS_AND_CLAIMS_PRESERVED", "NO_OWNER_STOP_OVERRIDE",
                         "SOURCE_CONTEXT_AND_IMMUTABLE_TEST_PINS", "PUBLISH_READBACK"):
                self.assertIn(gate, request["publisher_requirements"])
            self.assertTrue((Path(temp) / "relay" / (request["new_manifest_sha256"] + ".json")).is_file())
            self.assertEqual(list(Path(temp).glob("native_publish_entry_*.py")), [])

    def test_stale_or_tampered_refill_request_holds(self):
        args = list(fixture())
        args[6] = copy.deepcopy(args[6])
        args[6]["source_pins"] = {"NOX_PROJECT_SOURCE": {"work_progress.py": "0" * 64}}
        with self.assertRaisesRegex(ValueError, "REFILL_REQUEST_ID"):
            compile_fixture(tuple(args))

    def test_review_must_bind_exact_refill_request_bytes(self):
        args = list(fixture())
        args[10] = copy.deepcopy(args[10])
        args[10]["refill_request_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "EXACT_REVIEW_RECEIPT"):
            compile_fixture(tuple(args))

    def test_parent_spec_sha_must_match_existing_original_spec(self):
        args = list(fixture())
        args[2] = copy.deepcopy(args[2])
        args[2]["missions"][0]["parent_spec_sha256"] = "0" * 64
        args[3] = canonical_sha(args[2])
        args[10] = copy.deepcopy(args[10])
        args[10]["proposal_sha256"] = args[3]
        args[10]["reviewed_mission_ids"] = sorted(m["mission_id"] for m in args[2]["missions"])
        args[10]["immutable_verifier_sha256"] = producer.immutable_verifier_sha256(
            args[2]["missions"], args[4]["roots"])
        with self.assertRaisesRegex(ValueError, "ORIGINAL_SPEC_SHA_PIN"):
            compile_fixture(tuple(args))

    def test_duplicate_original_task_in_successor_is_rejected(self):
        args = list(fixture())
        args[2] = copy.deepcopy(args[2])
        duplicate = copy.deepcopy(args[2]["missions"][0])
        duplicate["mission_id"] = "second_plan_same_parent"
        args[2]["missions"].append(duplicate)
        args[3] = canonical_sha(args[2])
        args[10] = copy.deepcopy(args[10])
        args[10]["proposal_sha256"] = args[3]
        args[10]["reviewed_mission_ids"] = sorted(m["mission_id"] for m in args[2]["missions"])
        args[10]["immutable_verifier_sha256"] = producer.immutable_verifier_sha256(
            args[2]["missions"], args[4]["roots"])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ORIGINAL_TASK"):
            compile_fixture(tuple(args))

    def test_live_or_historical_child_id_blocks_parent_replay(self):
        args = list(fixture())
        args[6] = copy.deepcopy(args[6])
        args[6]["outcomes"].append({"task_id": "0B04.relay.older_plan.1234567890abcdef",
            "mission_id": "older_plan", "mission_revision": 1,
            "input_sha256": "c" * 64, "status": "blocked"})
        args[6]["request_id"] = producer.digest({
            "manifest_sha256": args[1], "source_pins": args[6]["source_pins"],
            "outcomes": args[6]["outcomes"],
            "original_task_states": args[6]["original_task_states"]})
        args[2] = copy.deepcopy(args[2])
        args[2]["request_id"] = args[6]["request_id"]
        args[3] = canonical_sha(args[2])
        args[7] = canonical_sha(args[6])
        args[10] = copy.deepcopy(args[10])
        args[10]["proposal_sha256"] = args[3]
        args[10]["refill_request_sha256"] = canonical_sha(args[6])
        args[10]["reviewed_mission_ids"] = sorted(m["mission_id"] for m in args[2]["missions"])
        args[10]["immutable_verifier_sha256"] = producer.immutable_verifier_sha256(
            args[2]["missions"], args[4]["roots"])
        with self.assertRaisesRegex(ValueError, "ORIGINAL_TASK_ALREADY_OBSERVED"):
            compile_fixture(tuple(args))

    def test_existing_original_task_state_blocks_replay(self):
        args = list(fixture())
        args[6] = copy.deepcopy(args[6])
        args[6]["original_task_states"] = [{"task_id": "0B04", "status": "blocked"}]
        args[6]["original_task_states_sha256"] = producer.digest(args[6]["original_task_states"])
        args[6]["request_id"] = producer.digest({
            "manifest_sha256": args[1], "source_pins": args[6]["source_pins"],
            "outcomes": args[6]["outcomes"],
            "original_task_states": args[6]["original_task_states"]})
        args[2] = copy.deepcopy(args[2])
        args[2]["request_id"] = args[6]["request_id"]
        args[3] = canonical_sha(args[2])
        args[7] = canonical_sha(args[6])
        args[10] = copy.deepcopy(args[10])
        args[10]["proposal_sha256"] = args[3]
        args[10]["refill_request_sha256"] = args[7]
        with self.assertRaisesRegex(ValueError, "ORIGINAL_TASK_ALREADY_OBSERVED"):
            compile_fixture(tuple(args))

    def test_selector_binds_original_task_state_into_refill_request_id(self):
        previous, _ = read(PREVIOUS)
        previous["missions"] = []
        previous_sha = producer.digest(previous)
        state = {"0B04": {"status": "blocked"}}
        result = producer.validate_manifest(previous)
        self.assertIs(result, previous)
        selected = __import__("owner_systemic_refill").select_next(
            previous, state, {}, {"slots_available": 1, "callback_sha256": "a" * 64,
                                  "now": 1, "manifest_sha256": previous_sha})
        request = selected["refill_request"]
        self.assertEqual(selected["state"], "REFILL_REQUIRED")
        self.assertEqual(request["original_task_states"],
                         [{"task_id": "0B04", "status": "blocked"}])
        self.assertEqual(request["request_id"], producer.digest({
            "manifest_sha256": previous_sha, "source_pins": {}, "outcomes": [],
            "original_task_states": request["original_task_states"]}))

    def test_review_requires_settled_owner_readback_and_immutable_verifier(self):
        args = list(fixture())
        args[10] = copy.deepcopy(args[10])
        args[10]["previous_claims_settled"] = False
        with self.assertRaisesRegex(ValueError, "OWNER_READBACK_RECEIPT"):
            compile_fixture(tuple(args))
        args = list(fixture())
        args[10] = copy.deepcopy(args[10])
        args[10]["immutable_verifier_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "IMMUTABLE_VERIFIER_REVIEW_PIN"):
            compile_fixture(tuple(args))

    def test_reviewed_registry_hash_and_mission_set_are_exact(self):
        args = list(fixture())
        args[10] = copy.deepcopy(args[10])
        args[10]["registry_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "EXACT_REGISTRY_REVIEW"):
            compile_fixture(tuple(args))
        args = list(fixture())
        args[10] = copy.deepcopy(args[10])
        args[10]["reviewed_mission_ids"] = ["unreviewed"]
        with self.assertRaisesRegex(ValueError, "REVIEWED_MISSION_SET"):
            compile_fixture(tuple(args))


if __name__ == "__main__":
    unittest.main()
