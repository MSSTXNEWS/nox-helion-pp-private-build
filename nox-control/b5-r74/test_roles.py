import io
import json
import os
from pathlib import Path
import unittest
import zipfile
from stage_roles import compose, bridge_bytes, sha, BRIDGE_SHA, EVIDENCE_SHA

class StagedRoles(unittest.TestCase):
    def test_exact_roles_and_tamper(self):
        evidence = Path(os.environ["R73_EVIDENCE"]).read_bytes()
        bridge = bridge_bytes(os.environ["B5_REPO"])
        raw = compose(evidence, bridge)
        self.assertEqual(raw, compose(evidence, bridge))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(set(archive.namelist()), {
                "evidence/b5-r73-staging.zip", "physical-bridge/b3_r64_eof_candidate.js",
                "r74-role-manifest.json"})
            self.assertEqual(sha(archive.read("evidence/b5-r73-staging.zip")), EVIDENCE_SHA)
            self.assertEqual(sha(archive.read("physical-bridge/b3_r64_eof_candidate.js")), BRIDGE_SHA)
            manifest = json.loads(archive.read("r74-role-manifest.json"))
            self.assertEqual([f["role"] for f in manifest["files"]],
                             ["completed_dialog_evidence", "physical_bridge_candidate"])
            for key in ("native_accepted", "installation_authorized", "next_post_allowed"):
                self.assertIs(manifest[key], False)
            self.assertEqual(manifest["browser_role"], "external_required")
            with zipfile.ZipFile(io.BytesIO(archive.read("evidence/b5-r73-staging.zip"))) as inner:
                self.assertIn("manifest.json", inner.namelist())
                self.assertEqual(len(json.loads(inner.read("manifest.json"))["files"]), 10)
        with self.assertRaisesRegex(ValueError, "HOLD_R73_EVIDENCE_PIN"):
            compose(evidence+b"x", bridge)
        with self.assertRaisesRegex(ValueError, "HOLD_R64_PHYSICAL_BRIDGE_PIN"):
            compose(evidence, bridge[:-1]+bytes([bridge[-1]^1]))
        with self.assertRaisesRegex(ValueError, "HOLD_R64_PHYSICAL_BRIDGE_PIN"):
            compose(evidence, evidence)

if __name__ == "__main__":
    unittest.main()
