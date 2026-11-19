"""Fail-closed source-only tests for REFILL_REQUIRED diagnostics and compilation."""
import copy
import contextlib
import fcntl
import io
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))
import owner_systemic_taskpack as producer
import owner_systemic_relay_publish as publisher
from owner_systemic_refill_eligibility import (
    strict_parent_registry, eligibility_ledger, proposal_predicate_diff,
    special_candidate_gaps,
)
from owner_systemic_refill import acceptance_mapping_valid
import owner_systemic_refill as refill

OPERATOR_SPEC = importlib.util.spec_from_file_location(
    "owner_native_operator_marker_check", ROOT.parent / "owner_native_operator.py")
OPERATOR = importlib.util.module_from_spec(OPERATOR_SPEC)
assert OPERATOR_SPEC.loader is not None
OPERATOR_SPEC.loader.exec_module(OPERATOR)

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
    def test_owner_snapshot_is_recent_exactly_bound_and_claim_free(self):
        now = 1800000000
        snapshot = {'schema':producer.OWNER_SNAPSHOT_SCHEMA,'owner_id':60509551,
            'observed_at':now-60,'config_sha256':'a'*64,
            'previous_manifest_sha256':'b'*64,'registry_sha256':'c'*64,
            'source_files_sha256':'d'*64,'refill_request_id':'e'*64,
            'original_task_states_sha256':'f'*64,'process_identity_sha256':'1'*64,
            'native_readback_sha256':'2'*64,'active_claim_count':0}
        self.assertEqual(producer.validate_owner_snapshot(snapshot,now=now,
            expected_previous_sha='b'*64,expected_refill_request='e'*64,
            expected_registry_sha='c'*64,expected_source_sha='d'*64,
            expected_native_readback_sha='2'*64),snapshot)
        for changed,reason in (({**snapshot,'observed_at':now-601},'OWNER_SNAPSHOT_STALE'),
            ({**snapshot,'active_claim_count':1},'OWNER_SNAPSHOT_ACTIVE_CLAIMS'),
            ({**snapshot,'previous_manifest_sha256':'9'*64},'OWNER_SNAPSHOT_BINDING'),
            ({**snapshot,'extra':'ignored'},'OWNER_SNAPSHOT_SHAPE')):
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                producer.validate_owner_snapshot(changed,now=now,
                    expected_previous_sha='b'*64,expected_refill_request='e'*64,
                    expected_registry_sha='c'*64,expected_source_sha='d'*64,
                    expected_native_readback_sha='2'*64)
        with self.assertRaisesRegex(RuntimeError,'OWNER_SNAPSHOT_STALE_OR_IDENTITY'):
            publisher.validate_owner_snapshot(snapshot,now=now+601)

    def test_live_cgroup_budget_holds_below_two_gib_headroom(self):
        now=1800000000
        sample={'schema':'NOX_BOUNDED_CPU_BUDGET_V1','source':'cgroup_v2',
            'instance_id':60509551,'observed_at':now-1,
            'current_bytes':10*1024**3,'max_bytes':10*1024**3+27*1024**2,
            'minimum_headroom_bytes':2*1024**3}
        with self.assertRaisesRegex(RuntimeError,
                'HOLD_SYSTEMIC_PUBLISH_RESOURCE_HEADROOM_BELOW_MINIMUM'):
            publisher.require_budget_headroom(sample,now=now)
        stale={**sample,'observed_at':now-6,
               'max_bytes':sample['current_bytes']+3*1024**3}
        with self.assertRaisesRegex(RuntimeError,
                'HOLD_SYSTEMIC_PUBLISH_RESOURCE_SNAPSHOT_FIELDS_OR_STALE'):
            publisher.require_budget_headroom(stale,now=now)
        sample['max_bytes']=sample['current_bytes']+3*1024**3
        self.assertEqual(publisher.require_budget_headroom(sample,now=now)['headroom_bytes'],
                         3*1024**3)

    def test_package_write_reads_fresh_budget_immediately_before_atomic_write(self):
        class RecordingHelper:
            def __init__(self, headroom): self.events=[]; self.headroom=headroom
            def read_budget_snapshot(self, config):
                self.events.append('budget')
                now=time.time()
                return {'schema':'NOX_BOUNDED_CPU_BUDGET_V1','source':'cgroup_v2',
                    'instance_id':60509551,'observed_at':now,
                    'current_bytes':10*1024**3,'max_bytes':10*1024**3+self.headroom,
                    'minimum_headroom_bytes':2*1024**3}
            def atomic(self, path, raw): self.events.append('atomic')

        healthy=RecordingHelper(3*1024**3)
        gate=publisher.write_package_with_budget_gate(healthy,'pkg',b'bytes',{})
        self.assertEqual(gate['state'],'PASS')
        self.assertEqual(healthy.events,['budget','atomic'])
        low=RecordingHelper(27*1024**2)
        with self.assertRaisesRegex(RuntimeError,'RESOURCE_HEADROOM_BELOW_MINIMUM'):
            publisher.write_package_with_budget_gate(low,'pkg',b'bytes',{})
        self.assertEqual(low.events,['budget'])

    def test_publish_cas_rechecks_budget_then_snapshot_age_and_lock_identity(self):
        class BudgetReader:
            def __init__(self): self.calls=0
            def read_budget_snapshot(self, config):
                self.calls+=1; now=time.time()
                return {'schema':'NOX_BOUNDED_CPU_BUDGET_V1','source':'cgroup_v2',
                    'instance_id':60509551,'observed_at':now,
                    'current_bytes':10*1024**3,'max_bytes':13*1024**3,
                    'minimum_headroom_bytes':2*1024**3}
        now=time.time()
        snapshot={'schema':producer.OWNER_SNAPSHOT_SCHEMA,'owner_id':60509551,
            'observed_at':now-1,'config_sha256':'a'*64,
            'previous_manifest_sha256':'b'*64,'registry_sha256':'c'*64,
            'source_files_sha256':'d'*64,'refill_request_id':'e'*64,
            'original_task_states_sha256':'f'*64,'process_identity_sha256':'1'*64,
            'native_readback_sha256':'2'*64,'active_claim_count':0}
        original_root=publisher.ROOT
        with tempfile.TemporaryDirectory() as directory:
            publisher.ROOT=Path(directory)
            state=Path(directory)/'state'; state.mkdir(mode=0o700)
            lock=state/'owner_maintenance.lock'; lock.write_bytes(b'lock')
            lock.chmod(0o600)
            state_dir_fd=os.open(state,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            fd=os.open(lock.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=state_dir_fd)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                helper=BudgetReader()
                result=publisher.verify_publish_cas_preconditions(
                    helper,{},snapshot,fd,lock,state_dir_fd)
                self.assertEqual(result['state'],'PASS')
                self.assertEqual(helper.calls,1)
                stale={**snapshot,'observed_at':time.time()-601}
                with self.assertRaisesRegex(RuntimeError,'OWNER_SNAPSHOT_STALE_OR_IDENTITY'):
                    publisher.verify_publish_cas_preconditions(
                        helper,{},stale,fd,lock,state_dir_fd)
                self.assertEqual(helper.calls,2)

                moved=Path(directory)/'replacement'; moved.write_bytes(b'foreign')
                moved.chmod(0o600); os.replace(moved,lock)
                with self.assertRaisesRegex(RuntimeError,'LEASE_IDENTITY'):
                    publisher.verify_publish_cas_preconditions(
                        helper,{},snapshot,fd,lock,state_dir_fd)
                self.assertEqual(helper.calls,3)
            finally:
                os.close(fd)
                os.close(state_dir_fd)
                publisher.ROOT=original_root

    def test_config_cas_rechecks_lease_after_staging_and_uses_anchored_dirfd(self):
        class BudgetReader:
            def read_budget_snapshot(self, config):
                now=time.time()
                return {'schema':'NOX_BOUNDED_CPU_BUDGET_V1','source':'cgroup_v2',
                    'instance_id':60509551,'observed_at':now,
                    'current_bytes':10*1024**3,'max_bytes':13*1024**3,
                    'minimum_headroom_bytes':2*1024**3}
        now=time.time()
        snapshot={'schema':publisher.OWNER_SNAPSHOT_SCHEMA,'owner_id':60509551,
            'observed_at':now-1,'config_sha256':'a'*64,
            'previous_manifest_sha256':'b'*64,'registry_sha256':'c'*64,
            'source_files_sha256':'d'*64,'refill_request_id':'e'*64,
            'original_task_states_sha256':'f'*64,'process_identity_sha256':'1'*64,
            'native_readback_sha256':'2'*64,'active_claim_count':0}
        original_root,original_config=publisher.ROOT,publisher.CONFIG
        with tempfile.TemporaryDirectory() as directory:
            publisher.ROOT=Path(directory)
            config_dir=Path(directory)/'config'; config_dir.mkdir(mode=0o700)
            state=Path(directory)/'state'; state.mkdir(mode=0o700)
            publisher.CONFIG=config_dir/'owner_native_subagents.json'
            old=b'{"before":true}'
            new=b'{"after":true}'
            publisher.CONFIG.write_bytes(old); publisher.CONFIG.chmod(0o600)
            lock=state/'owner_maintenance.lock'; lock.write_bytes(b'lock')
            lock.chmod(0o600)
            state_dir_fd=os.open(state,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            fd=os.open(lock.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=state_dir_fd)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                budget=publisher.atomic_owner_config(
                    BudgetReader(),new,old,snapshot,fd,lock,state_dir_fd)
                self.assertEqual(budget['state'],'PASS')
                self.assertEqual(publisher.CONFIG.read_bytes(),new)

                publisher.CONFIG.write_bytes(old)
                def replace_lease_between_early_check_and_cas():
                    replacement=Path(directory)/'replacement'
                    replacement.write_bytes(b'other-owner')
                    replacement.chmod(0o600)
                    os.replace(replacement,lock)
                with self.assertRaisesRegex(RuntimeError,'LEASE_IDENTITY'):
                    publisher.atomic_owner_config(
                        BudgetReader(),new,old,snapshot,fd,lock,state_dir_fd,
                        before_final_gate=replace_lease_between_early_check_and_cas)
                self.assertEqual(publisher.CONFIG.read_bytes(),old)
            finally:
                os.close(fd)
                os.close(state_dir_fd)
                publisher.ROOT, publisher.CONFIG=original_root,original_config

    def test_backup_gate_and_exact_retry_survive_precommit_hold(self):
        class BackupHelper:
            def __init__(self):
                self.budget_calls=0; self.atomic_calls=0; self.headroom=3*1024**3
            def read_budget_snapshot(self, config):
                self.budget_calls+=1; now=time.time()
                return {'schema':'NOX_BOUNDED_CPU_BUDGET_V1','source':'cgroup_v2',
                    'instance_id':60509551,'observed_at':now,
                    'current_bytes':10*1024**3,
                    'max_bytes':10*1024**3+self.headroom,
                    'minimum_headroom_bytes':2*1024**3}
            def atomic(self, path, raw):
                self.atomic_calls+=1; path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(raw); path.chmod(0o600)
            def read_regular(self, path, maximum):
                raw=Path(path).read_bytes()
                if len(raw)>maximum: raise RuntimeError('oversized')
                return raw
        now=time.time()
        snapshot={'schema':publisher.OWNER_SNAPSHOT_SCHEMA,'owner_id':60509551,
            'observed_at':now-1,'config_sha256':'a'*64,
            'previous_manifest_sha256':'b'*64,'registry_sha256':'c'*64,
            'source_files_sha256':'d'*64,'refill_request_id':'e'*64,
            'original_task_states_sha256':'f'*64,'process_identity_sha256':'1'*64,
            'native_readback_sha256':'2'*64,'active_claim_count':0}
        original_root=publisher.ROOT
        with tempfile.TemporaryDirectory() as directory:
            publisher.ROOT=Path(directory)
            state=Path(directory)/'state'; state.mkdir(mode=0o700)
            lock=state/'owner_maintenance.lock'; lock.write_bytes(b'lock')
            lock.chmod(0o600)
            state_dir_fd=os.open(state,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            fd=os.open(lock.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=state_dir_fd)
            helper=BackupHelper(); backup=state/'dispatcher'/'rollback'/'request-123'
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                helper.headroom=27*1024**2
                with self.assertRaisesRegex(RuntimeError,'RESOURCE_HEADROOM_BELOW_MINIMUM'):
                    publisher.ensure_exact_backup(
                        helper,backup,b'old-config',{},snapshot,fd,lock,state_dir_fd)
                self.assertFalse(backup.exists())
                self.assertEqual(helper.atomic_calls,0)
                helper.headroom=3*1024**3
                first=publisher.ensure_exact_backup(
                    helper,backup,b'old-config',{},snapshot,fd,lock,state_dir_fd)
                self.assertEqual(first['state'],'WRITTEN')
                self.assertEqual(first['resource_gate']['state'],'PASS')
                self.assertEqual(helper.budget_calls,2)
                self.assertEqual(helper.atomic_calls,1)
                helper.headroom=27*1024**2
                with self.assertRaisesRegex(RuntimeError,'RESOURCE_HEADROOM_BELOW_MINIMUM'):
                    publisher.verify_publish_cas_preconditions(
                        helper,{},snapshot,fd,lock,state_dir_fd)
                self.assertEqual(backup.joinpath('config.json').read_bytes(),b'old-config')
                helper.headroom=3*1024**3
                # A pre-CAS HOLD leaves an exact backup which a retry may reuse.
                second=publisher.ensure_exact_backup(
                    helper,backup,b'old-config',{},snapshot,fd,lock,state_dir_fd)
                self.assertEqual(second,{'state':'REUSED_EXACT','resource_gate':None})
                self.assertEqual(helper.budget_calls,3)
                self.assertEqual(helper.atomic_calls,1)
                (backup/'config.json').write_bytes(b'foreign-config')
                with self.assertRaisesRegex(RuntimeError,'BACKUP_CONTENT_CHANGED'):
                    publisher.ensure_exact_backup(
                        helper,backup,b'old-config',{},snapshot,fd,lock,state_dir_fd)
            finally:
                os.close(fd)
                os.close(state_dir_fd)
                publisher.ROOT=original_root

    def test_persist_receipt_rejects_hostile_hold_suffix(self):
        class ReceiptSink:
            def __init__(self): self.raw=None
            def atomic(self,path,raw): self.raw=raw
        sink=ReceiptSink();output=io.StringIO()
        receipt={'state':'HOLD_SYSTEMIC_PUBLISH_OWNER_STOP:injected-suffix',
                 'manifest_sha256':'3'*64}
        with contextlib.redirect_stdout(output):
            publisher.persist_receipt(sink,'42',receipt)
        stored=json.loads(sink.raw)
        self.assertEqual(stored['state'],'HOLD_SYSTEMIC_PUBLISH_INTERNAL')
        self.assertIn('NOX_MAINT_SYSTEMIC_RELAY_PUBLISH=',output.getvalue())

    def test_hold_receipt_is_emitted_for_stale_candidate(self):
        class ReceiptSink:
            def __init__(self): self.raw=None
            def atomic(self,path,raw): self.raw=raw
        now=1800000000
        snapshot={'schema':producer.OWNER_SNAPSHOT_SCHEMA,'owner_id':60509551,
            'observed_at':now-601,'config_sha256':'a'*64,
            'previous_manifest_sha256':'b'*64,'registry_sha256':'c'*64,
            'source_files_sha256':'d'*64,'refill_request_id':'e'*64,
            'original_task_states_sha256':'f'*64,'process_identity_sha256':'1'*64,
            'native_readback_sha256':'2'*64,'active_claim_count':0}
        receipt={'state':'PREFLIGHT','manifest_sha256':'3'*64}
        sink=ReceiptSink();output=io.StringIO()
        with self.assertRaisesRegex(RuntimeError,'OWNER_SNAPSHOT_STALE_OR_IDENTITY'):
            try:
                publisher.validate_owner_snapshot(snapshot,now=now)
            except BaseException as exc:
                receipt['state']='HOLD_SYSTEMIC_PUBLISH_' + str(exc).removeprefix('HOLD_SYSTEMIC_PUBLISH_')
                with contextlib.redirect_stdout(output):
                    publisher.persist_receipt(sink,'42',receipt)
                raise
        self.assertEqual(json.loads(sink.raw)['state'],'HOLD_SYSTEMIC_PUBLISH_OWNER_SNAPSHOT_STALE_OR_IDENTITY')
        self.assertIn('NOX_MAINT_SYSTEMIC_RELAY_PUBLISH=',output.getvalue())

    def test_publish_completion_marker_matches_reflex_action_only(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            publisher.emit_publish_complete_marker()
        stdout=output.getvalue()
        expected='NOX_MAINT_REFLEX_PUBLISH_COMPLETE=true'
        repair='NOX_MAINT_REPAIR_COMPLETE=true'
        self.assertTrue(OPERATOR._has_exact_terminal_completion_marker(stdout,expected))
        self.assertFalse(OPERATOR._has_exact_terminal_completion_marker(stdout,repair))
        self.assertFalse(OPERATOR._has_exact_terminal_completion_marker(repair+'\n',expected))

    def test_successor_route_rejects_zero_or_multiple_parent_missions(self):
        for proposals in ([],[{},{}]):
            with self.subTest(count=len(proposals)),self.assertRaisesRegex(
                    ValueError,'EXACTLY_ONE_SUCCESSOR_REQUIRED'):
                producer.bind_missions(proposals,{}, {'parents':{}},{})
        with self.assertRaisesRegex(RuntimeError,'EXACTLY_ONE_SUCCESSOR_REQUIRED'):
            publisher.require_exactly_one_successor({'missions':[]})
        with self.assertRaisesRegex(RuntimeError,'EXACTLY_ONE_SUCCESSOR_REQUIRED'):
            publisher.require_exactly_one_successor({'missions':[{},{}]})

    def test_native_receipt_contract_binds_original_source_and_test_shas(self):
        mission={'parent_task_id':'I-39','mission_id':'minhash_guard','revision':1,
            'root_id':'NOX_PROJECT_SOURCE','context':[
                {'path':'forge_split_guard.py','sha256':'a'*64},
                {'path':'test_forge_split_guard.py','sha256':'b'*64}],
            'editable_paths':['forge_split_guard.py'],
            'instruction':'Add the grounded MinHash leakage check.',
            'verification':{'modules':['test_forge_split_guard'],'min_tests':1},
            'registered_acceptance':'MinHash split without leakage',
            'parent_spec_sha256':'c'*64}
        contract=producer.native_receipt_contract(mission,manifest_revision=4,
            previous_sha='d'*64,registry_sha='e'*64,review_sha='f'*64)
        self.assertEqual(contract['original_task_id'],'I-39')
        self.assertEqual(contract['successor_task_id'].split('.relay.')[0],'I-39')
        self.assertEqual(contract['source_sha256'],producer.digest(contract['source_pins']))
        self.assertEqual(contract['test_sha256'],producer.digest(contract['test_pins']))
        self.assertEqual(contract['test_pins'][0]['sha256'],'b'*64)
        self.assertFalse(contract['acceptance_recorded'])
        self.assertFalse(contract['required_receipt']['original_task_accepted'])
        self.assertTrue(contract['required_receipt']['s03']['native_verified'])
        self.assertTrue(contract['required_receipt']['receipt'][
            'worker_result.project_evidence.tests.passed'])
        native=publisher.native_receipt_contract(mission,manifest_revision=4,
            previous_sha='d'*64,registry_sha='e'*64,review_sha='f'*64,refill=refill)
        self.assertEqual(native,contract)

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
