#!/usr/bin/env python3
"""T11 READ ONLY fail-closed regression; no network and no GitLab token."""
import copy
import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().with_name("NOX_V16_T11_GITLAB_READONLY_AUDIT.py")
SPEC = importlib.util.spec_from_file_location("nox_t11_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class GateTests(unittest.TestCase):
    def setUp(self):
        self.handoff = {
            "history": {"migration_only_files": [
                {"path": "file_%02d" % i} for i in range(27)
            ], "original_source_part_blobs": [
                {"path":"source_0%d.part"%i,"sha":"dead"} for i in range(3)
            ]},
            "ci": {
                "historical_gitlab_ci_blob_sha1": "ci",
                "historical_gitlab_entrypoint_blob_sha1": "entry",
            }
        }
        self.proof = {
            "project_visible":True, "visibility":"private",
            "live_gitlab_head":"a"*40,
            "migration_live_head":"b"*40,
            "access_level":30, "migration_commit_preserved":True,
            "migration_unique_verified":27,"migration_unique_mismatches":[],
            "original_parts_verified":3,"original_parts_mismatches":[],
            "ci_git_blob":"ci","entrypoint_git_blob":"entry",
            "windows_runner_proven_online":True
        }
    def verify(self, changes, expected):
        obj = copy.deepcopy(self.proof)
        obj.update(changes)
        self.assertEqual(MODULE.evaluate_live_evidence(obj,self.handoff),expected)
        self.assertIs(obj["source_ready"], False)
        self.assertIs(obj["build_authorized"], False)
        return obj
    def test_complete_proof_still_denies_build(self):
        x=self.verify({},True)
        self.assertEqual(x["status"],"LIVE_MIGRATION_VERIFIED_NOT_SOURCE_READY")
    def test_missing_auth_permission_fails(self):
        x=self.verify({"access_level":None},False)
        self.assertIn("PROJECT_READ_PERMISSION_UNVERIFIED",x["evidence_errors"])
    def test_missing_last_file_fails(self):
        x=self.verify({"migration_unique_verified":26},False)
        self.assertIn("MIGRATION_27_BLOB_MISMATCH",x["evidence_errors"])
    def test_modified_original_part_fails(self):
        x=self.verify({"original_parts_verified":2},False)
        self.assertIn("ORIGINAL_3_PARTS_GIT_BLOB_MISMATCH",x["evidence_errors"])
    def test_ci_drift_fails(self):
        x=self.verify({"ci_git_blob":"tamper"},False)
        self.assertIn("CI_BLOB_DRIFT",x["evidence_errors"])
    def test_no_runner_fails(self):
        x=self.verify({"windows_runner_proven_online":False},False)
        self.assertIn("WINDOWS_RUNNER_NOT_PROVEN_ONLINE",x["evidence_errors"])
    def test_nonprivate_project_fails(self):
        x=self.verify({"visibility":"public"},False)
        self.assertIn("PROJECT_PRIVACY_UNVERIFIED",x["evidence_errors"])

if __name__=="__main__":
    unittest.main()
