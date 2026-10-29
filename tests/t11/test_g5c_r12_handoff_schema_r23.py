"""Offline fail-closed T11 R12 adapter checks; no GitLab calls or CI."""
import copy
import unittest
from coordination.t11.NOX_V16_T11_GITLAB_READONLY_AUDIT import verified_handoff_layout, EXPECTED_PROJECT, EXPECTED_MIGRATION_REF

class T11R12HandoffAdapter(unittest.TestCase):
    def setUp(self):
        self.data = {"schema":"NOX_FIN_ZAGR_V16_T11_GITLAB_FREE_SOURCE_HANDOFF_V1",
            "gitlab_target":{"url":"https://gitlab.com/"+EXPECTED_PROJECT,
                "historic_runner_tag":"saas-windows-medium-amd64"},
            "github_verified":{"historical_migration_ref":EXPECTED_MIGRATION_REF,
                "historical_migration_head_sha1":"f"*40,
                "migration_only_files":[{"path":"p"+str(i),"git_blob_sha1":"a"*40} for i in range(27)]}}
    def invalid(self, f):
        x=copy.deepcopy(self.data); f(x)
        with self.assertRaises((ValueError,KeyError,TypeError)):
            verified_handoff_layout(x)
    def test_existing_r12_schema(self):
        self.assertEqual(len(verified_handoff_layout(self.data)["history"]["migration_only_files"]),27)
    def test_generic_schema(self):
        z=verified_handoff_layout(self.data)
        self.assertEqual(verified_handoff_layout(z)["gitlab"]["path"],EXPECTED_PROJECT)
    def test_project_substitution(self):
        self.invalid(lambda x:x["gitlab_target"].update(url="https://gitlab.com/other/other"))
    def test_duplicate_path(self):
        self.invalid(lambda x:x["github_verified"]["migration_only_files"][1].update(path="p0"))
    def test_truncated_manifest(self):
        self.invalid(lambda x:x["github_verified"]["migration_only_files"].pop())
    def test_invalid_blob(self):
        self.invalid(lambda x:x["github_verified"]["migration_only_files"][0].update(git_blob_sha1="bad"))
    def test_migration_ref(self):
        self.invalid(lambda x:x["github_verified"].update(historical_migration_ref="wrong"))
    def test_invalid_migration_commit(self):
        self.invalid(lambda x:x["github_verified"].update(historical_migration_head_sha1="bad"))
    def test_unknown_schema(self):
        self.invalid(lambda x:x.update(schema="unknown"))

if __name__ == "__main__":
    unittest.main()
