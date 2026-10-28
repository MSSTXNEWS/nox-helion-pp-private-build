"""Offline proof of REPORT_GATE schema; synthetic fixtures NEVER claim actual Drive writes."""
import copy
import importlib.util
import pathlib
import sys
import unittest

FILE=pathlib.Path(__file__).resolve().parents[2]/"coordination/reporting/verify_run_report.py"
spec=importlib.util.spec_from_file_location("nox_v16_report_gate",FILE)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)

H="a"*64
G="b"*40
R="NOX-V16-OWNER2-RUN9-CYCLE1"
def fixture():
    return {
        "run_id":R,"owner":2,"trigger":"111111111",
        "cycle_count":9,"cycle_index":1,
        "instruction_version":"NOX-V16-REPORT-GATE-R1",
        "instructions_read":{
            "v16_revision":"doc-rev-v16","master_revision":"master-rev-history-HOLD",
            "e06_report_revision":"report-rev","e06_lessons_revision":"lessons-rev",
            "last_own_receipt":"old-owner-sha-receipt"
        },
        "learning":{
            "prior_run_id":"PREVIOUS-RUN","observed_error":"Previous fallback masked missing voice",
            "root_cause":"Host route not verified",
            "changed_method":"Require owner bound capability for each route",
            "regression_check":"No false status when model missing"
        },
        "tasks":[{
            "task_id":f"NOX-R2-REAL-{i:02d}",
            "owner":2,"status":"DONE",
            "description":f"Real source delta for task {i:02d} with owner receipt",
            "file_path":f"Packages/P02/owner_{i:02d}.py",
            "pre_sha256":H,"post_sha256":"c"*64,
            "patch_sha256":"d"*64,
            "receipt_id":f"RECEIPT-P02-{i}","test_result":"CI_PASS"
        } for i in range(1,11)],
        "evidence":{"git_commit_sha1":G,"component_result":"WINDOWS_COMPONENT_PASS",
                    "native_exe_accepted":False},
        "writes":{k:{"document_id":f"doc-{k}","run_id":R,
                      "readback":True,"readback_revision":f"rev-{k}"}
                  for k in ("own_report","e06_report","e06_lessons")},
        "quality_gates":{f"G{i}":{"status":"PASS","evidence":"Example synthetic only"}
                         for i in range(1,8)}
    }|{"writes":{**{k:{"document_id":f"doc-{k}","run_id":R,
                        "readback":True,"readback_revision":f"rev-{k}"}
                        for k in ("own_report","e06_report","e06_lessons")},
                 "master":{"status":"MASTER_HOLD","reason":"Historical master integrity unverified"}}}

class ValidatorTests(unittest.TestCase):
    def test_nine_units_mean_nine_cycles_not_nine_agents(self):
        x=module.validate(fixture())
        self.assertEqual((x["cycle_count"],x["cycle_index"]), (9,1))
        self.assertEqual(x["completed_unique_tasks"],10)
        self.assertEqual(x["result"],"SCHEMA_PASS_REMOTE_DRIVE_READBACK_STILL_REQUIRED")

    def test_ten_units_are_not_nine(self):
        x=fixture();x["trigger"]="1111111111"
        with self.assertRaisesRegex(module.ReportInvalid,"CYCLE_COUNT"):
            module.validate(x)

    def test_report_and_journal_run_identity_must_match(self):
        for field in ("own_report","e06_report","e06_lessons"):
            x=fixture();x["writes"][field]["run_id"]="WRONG-OWNER-RUN"
            with self.assertRaisesRegex(module.ReportInvalid,"RUN_ID_MISMATCH"):
                module.validate(x)

    def test_readback_mandatory(self):
        x=fixture();x["writes"]["e06_lessons"]["readback"]=False
        with self.assertRaisesRegex(module.ReportInvalid,"NO_READBACK"):
            module.validate(x)

    def test_master_hold_is_safe_without_destructive_overwrite(self):
        self.assertEqual(module.validate(fixture())["owner"],2)
        x=fixture();x["writes"]["master"]={"status":"PASS","readback_revision":"rev-master"}
        self.assertEqual(module.validate(x)["owner"],2)

    def test_reject_duplicate_ten_tasks(self):
        x=fixture();x["tasks"][1]["task_id"]=x["tasks"][0]["task_id"]
        with self.assertRaisesRegex(module.ReportInvalid,"DUPLICATE_TASK_ID"):
            module.validate(x)

    def test_pre_post_sha_and_native_acceptance_provenance(self):
        x=fixture();x["tasks"][0]["post_sha256"]=H
        with self.assertRaisesRegex(module.ReportInvalid,"NO_PHYSICAL_FILE_DELTA"):
            module.validate(x)
        x=fixture();x["evidence"]["native_exe_accepted"]=True
        with self.assertRaisesRegex(module.ReportInvalid,"EXE_SHA_REQUIRED"):
            module.validate(x)

    def test_prestart_and_previous_lesson_mandatory(self):
        x=fixture();x["instructions_read"].pop("master_revision")
        with self.assertRaisesRegex(module.ReportInvalid,"MISSING_MASTER_REVISION"):
            module.validate(x)
        x=fixture();x["learning"]["prior_run_id"]=R
        with self.assertRaisesRegex(module.ReportInvalid,"PREVIOUS_RUN"):
            module.validate(x)

    def test_conflicting_owner_and_fake_agent_not_granted(self):
        x=fixture();x["tasks"][0]["owner"]=6
        with self.assertRaisesRegex(module.ReportInvalid,"TASK_OWNER_MISMATCH"):
            module.validate(x)
        x=fixture();x["quality_gates"].pop("G7")
        with self.assertRaisesRegex(module.ReportInvalid,"SEVEN_PROCESS"):
            module.validate(x)

    def test_blocked_tasks_are_not_counted_complete(self):
        x=fixture();task=x["tasks"][0];task["status"]="HOLD";task["blocker"]="GPU unavailable"
        got=module.validate(x)
        self.assertEqual(got["completed_unique_tasks"],9)
        self.assertEqual(got["blocked_tasks"],1)

if __name__=="__main__":unittest.main()
