"""E06 R09: purely local SOURCE audit proofs, never a native host simulation."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from admission import (
    APPROVED_ROUTE_POLICY, BASE_COMMIT, Hold, run_read_only_audit,
    _snapshot_source_bytes, MAX_AUDIT_SOURCE_BYTES,
)


class SourceSnapshotR09Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.catalog = d / "catalog.json"
        self.bindings = d / "owner-map.json"
        self.actions = [
            {"taskId": f"NIP01-{i:02}", "routeId": route,
             "owner": owner, "risk": risk, "settings": []}
            for i, (route, owner, risk) in enumerate(APPROVED_ROUTE_POLICY, 1)
        ]
        self.rows = [
            {"taskId": x["taskId"], "routeId": x["routeId"],
             "owner": x["owner"], "sourceBinding": None}
            for x in self.actions
        ]
        self.cat_bytes = json.dumps({"version": "NOX-INTEGRATION-PACK-01", "actions": self.actions}).encode()
        self.map_bytes = json.dumps({"sourceBaseCommit": BASE_COMMIT, "routes": self.rows}).encode()
        self.catalog.write_bytes(self.cat_bytes)
        self.bindings.write_bytes(self.map_bytes)

    def test_all_50_routes_are_source_only_and_sha_of_exact_parsed_snapshot(self):
        r = run_read_only_audit(str(self.catalog), str(self.bindings))
        self.assertEqual(len(r["routes"]), 50)
        self.assertEqual(r["nativeIntegrated"], 0)
        self.assertEqual(r["catalogSha256"], hashlib.sha256(self.cat_bytes).hexdigest())
        self.assertEqual(r["bindingMapSha256"], hashlib.sha256(self.map_bytes).hexdigest())

    def test_no_second_read_can_substitute_digest_after_audited_bytes(self):
        # The previous implementation parsed read_text() then SHA'd an unrelated
        # read_bytes(), creating a digest that could describe different content.
        original = Path.read_bytes
        calls = {}
        def source_reads(p):
            calls[str(p)] = calls.get(str(p), 0) + 1
            if calls[str(p)] > 1:
                return b'ATTACKER_CHANGED_THE_FILE'
            return original(p)
        with patch.object(Path, 'read_bytes', source_reads):
            r = run_read_only_audit(str(self.catalog), str(self.bindings))
        self.assertEqual(calls.get(str(self.catalog), 0), 0)  # uses one fd snapshot, not Path.read_bytes
        self.assertEqual(calls.get(str(self.bindings), 0), 0)
        self.assertEqual(r["catalogSha256"], hashlib.sha256(self.cat_bytes).hexdigest())
        self.assertEqual(r["bindingMapSha256"], hashlib.sha256(self.map_bytes).hexdigest())

    def test_duplicate_json_key_is_hold_not_last_value_wins(self):
        self.catalog.write_bytes(self.cat_bytes.replace(b'"version":', b'"version": "x", "version":'))
        with self.assertRaisesRegex(Hold, "AUDIT_DUPLICATE_JSON_KEY"):
            run_read_only_audit(str(self.catalog), str(self.bindings))

    def test_non_utf8_source_fails_closed(self):
        self.catalog.write_bytes(b'\\xff' + self.cat_bytes)
        with self.assertRaisesRegex(Hold, "AUDIT_INVALID_UTF8_JSON"):
            run_read_only_audit(str(self.catalog), str(self.bindings))

    def test_symlink_parent_and_source_rejected(self):
        d = Path(self.tmp.name)
        target_link = d / "alias.json"
        try:
            target_link.symlink_to(self.catalog)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks not available in this runner')
        with self.assertRaisesRegex(Hold, 'AUDIT_SOURCE_REPARSE_POINT'):
            _snapshot_source_bytes(target_link)
        linked_dir = d / 'linked'
        linked_dir.symlink_to(d, target_is_directory=True)
        with self.assertRaisesRegex(Hold, 'AUDIT_SOURCE_REPARSE_POINT'):
            _snapshot_source_bytes(linked_dir / 'catalog.json')

    def test_folder_and_oversized_source_denied(self):
        with self.assertRaises(Hold):
            _snapshot_source_bytes(Path(self.tmp.name))
        self.catalog.write_bytes(b' ' * (MAX_AUDIT_SOURCE_BYTES + 1))
        with self.assertRaisesRegex(Hold, 'AUDIT_SOURCE_NOT_BOUNDED_REGULAR_FILE|AUDIT_SOURCE_TOO_LARGE'):
            run_read_only_audit(str(self.catalog), str(self.bindings))

    def test_missing_file_denied_without_reporting_hash(self):
        self.bindings.unlink()
        with self.assertRaisesRegex(Hold, 'INVALID_SOURCE_FILE'):
            run_read_only_audit(str(self.catalog), str(self.bindings))


if __name__ == '__main__':
    unittest.main()
