"""B04: pin current original OneHost P03 discovery, never authorize weights.

This guard compares source-locked Git blobs and existing discovery-only
contracts. It is not a Windows/NSIS/model-weights acceptance test.
"""
import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
STAGER = "coordination/e06/stage_native_stdio.py"
CATALOG = "Packages/P03/Source/python-host/catalog30.discovery.json"
MODEL = "Packages/P03/Source/P03.ModelCenter/ModelCatalog.cs"


def git_blob(relative):
    process = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD:" + relative],
        capture_output=True, text=True, timeout=20, check=True)
    result = process.stdout.strip().lower()
    if re.fullmatch(r"[0-9a-f]{40}", result) is None:
        raise ValueError("B04_UNVERIFIED_SOURCE_GIT_BLOB")
    return result


class NativeCatalogOwnerPin(unittest.TestCase):
    def test_stager_pins_actual_discovery_git_blob(self):
        source = (ROOT / STAGER).read_text(encoding="utf-8")
        found = re.findall(
            r"(?m)^\s*\('Packages/P03/Source/python-host/catalog30\.discovery\.json', "
            r"'catalog30\.discovery\.json', '([0-9a-f]{40})'\),$",
            source)
        self.assertEqual(found, [git_blob(CATALOG)])
        self.assertIn("pinned_bytes(src,blob)", source)
        self.assertIn("E06_NATIVE_OWNER_BLOB_SHA_HOLD", source)

    def test_discovery_not_promoted_to_unreviewed_install(self):
        catalog = json.loads((ROOT / CATALOG).read_text(encoding="utf-8"))
        self.assertEqual(catalog["sourceGitBlobSha1"], git_blob(MODEL))
        self.assertEqual(catalog["sourceType"], "discovery_only")
        rows = catalog["models"]
        self.assertEqual(len(rows), 31)
        self.assertEqual(len({row["id"] for row in rows}), 31)
        self.assertTrue(all(row["reviewStatus"] == "REVIEW_REQUIRED"
                            and row["downloadEligible"] is False
                            for row in rows))


if __name__ == "__main__":
    unittest.main()
