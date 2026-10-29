"""G3-A R13: read-only owner-preimage and native JSON contract checks."""
import ast
import json
import unittest
import patch_native_bridge_strict_json_g3a as patch

SAMPLE = '''import json
ALLOWED_ROUTES = tuple(range(50))
assert len(ALLOWED_ROUTES) == 50
APPROVED_NATIVE_POLICY = tuple(range(50))
class HostDenied(PermissionError):
    """Native host refused permission, consent or session."""
class Example:
    def execute(self, payload, session):
        raw = json.dumps(payload).encode("utf-8")
        frozen_payload = json.loads(raw)
        risk = "dangerous"
        if risk in ("sensitive", "dangerous") and "training.start" not in session.private_approved:
            raise HostDenied("Native sensitive action scope required")
        if risk == "dangerous" and (
            not callable(self.native_approve) or
            self.native_approve(session,route,json.loads(raw)) is not True):
            raise HostDenied("Fresh native action approval required")
        return frozen_payload
'''.encode()

class G3AR13StrictJsonSourcePatch(unittest.TestCase):
    def prepared(self):
        candidate = patch.propose_bytes(SAMPLE, expected_git_blob_sha1=patch.git_blob_sha1(SAMPLE)).decode()
        ast.parse(candidate)
        return candidate

    def test_g3a_r13_original_lossy_conversion(self):
        self.assertEqual(json.loads(json.dumps({"1": "allow", 1: "deny"})), {"1": "deny"})

    def test_g3a_r13_top_nested_guard_source_present(self):
        source = self.prepared()
        self.assertIn('if key in result:', source)
        self.assertIn('raise HostDenied("Duplicate native JSON property")', source)
        self.assertIn('object_pairs_hook=_reject_duplicate_native_json_members', source)

    def test_g3a_r13_approval_and_owner_both_guarded(self):
        source = self.prepared()
        self.assertEqual(source.count('object_pairs_hook=_reject_duplicate_native_json_members'), 2)
        self.assertIn('Fresh native action approval required', source)

    def test_g3a_r13_stale_source_blocked(self):
        with self.assertRaisesRegex(ValueError, 'STALE_OR_UNAUTHORIZED'):
            patch.propose_bytes(SAMPLE)

    def test_g3a_r13_noloss_and_acl_still_present(self):
        source = self.prepared()
        for contract in ('assert len(ALLOWED_ROUTES) == 50', 'APPROVED_NATIVE_POLICY',
                         'session.private_approved', 'Native sensitive action scope required'):
            self.assertIn(contract, source)

    def test_g3a_r13_patch_diff_has_only_expected_contract(self):
        diff = patch.proposed_unified_diff(SAMPLE, expected_git_blob_sha1=patch.git_blob_sha1(SAMPLE))
        self.assertIn('--- a/proposals/NOX-PACK01-50/native_bridge.py', diff)
        self.assertIn('+++ b/proposals/NOX-PACK01-50/native_bridge.py', diff)
        self.assertIn('+def _reject_duplicate_native_json_members(pairs):', diff)

if __name__ == '__main__':
    unittest.main(verbosity=2)
