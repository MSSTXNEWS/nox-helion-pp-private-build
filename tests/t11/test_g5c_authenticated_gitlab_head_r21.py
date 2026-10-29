"""T11 read-only evidence classifier regression; never calls GitLab or starts CI."""
import unittest
from coordination.t11.NOX_V16_T11_GITLAB_READONLY_AUDIT import evidence_readback_valid, EXPECTED_PROJECT
class G5CAuthenticatedHeadGateR21(unittest.TestCase):
    def valid(self):
        return {"authenticated_identity_verified": True, "project_visible": True,
                "project_path": EXPECTED_PROJECT, "effective_access_level": 30,
                "live_gitlab_head": "a" * 40, "migration_live_head": "b" * 40}
    def test_authenticated(self): self.assertTrue(evidence_readback_valid(self.valid()))
    def test_anonymous(self):
        x=self.valid(); x["authenticated_identity_verified"]=False
        self.assertFalse(evidence_readback_valid(x))
    def test_no_default_head(self):
        x=self.valid(); x["live_gitlab_head"]=None
        self.assertFalse(evidence_readback_valid(x))
    def test_no_migration_head(self):
        x=self.valid(); x["migration_live_head"]=None
        self.assertFalse(evidence_readback_valid(x))
    def test_no_rights(self):
        x=self.valid(); x["effective_access_level"]=None
        self.assertFalse(evidence_readback_valid(x))
    def test_foreign_project(self):
        x=self.valid(); x["project_path"]="other/project"
        self.assertFalse(evidence_readback_valid(x))
    def test_non_sha(self):
        x=self.valid(); x["live_gitlab_head"]="wrong"
        self.assertFalse(evidence_readback_valid(x))
if __name__ == "__main__": unittest.main()
