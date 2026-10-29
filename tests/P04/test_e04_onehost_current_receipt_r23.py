"""P04 source-only historical receipt reconciliation (no native QA attestation).

Run: python -m unittest discover -s tests/P04 -p test_e04_onehost_current_receipt_r23.py
Git tree verification intentionally pins the source HEAD stored in the receipt;
a later mutable branch HEAD is not accepted automatically.
"""
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "Packages/P04/E04_ONEHOST_CURRENT_HEAD_R23_RECEIPT.json"
HEX40 = re.compile(r"[0-9a-f]{40}$")
PRODUCT_PREFIXES = ("Packages/P04/", "tests/P04/")


def git(*arguments):
    result = subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15, check=False,
    )
    if result.returncode:
        raise AssertionError("PINNED_GIT_OBJECT_UNAVAILABLE")
    return result.stdout.decode("ascii").strip()


def require_pinned_receipt(record):
    head = record.get("source_head")
    tree = record.get("source_tree")
    if not isinstance(head, str) or not HEX40.fullmatch(head):
        raise AssertionError("INVALID_SOURCE_HEAD")
    if not isinstance(tree, str) or not HEX40.fullmatch(tree):
        raise AssertionError("INVALID_SOURCE_TREE")
    if git("rev-parse", head + "^{tree}") != tree:
        raise AssertionError("SOURCE_TREE_MISMATCH")
    files = record.get("files")
    if not isinstance(files, list) or len(files) != 4:
        raise AssertionError("SOURCE_FILE_COUNT_MISMATCH")
    seen = set()
    matches = evolved = 0
    for item in files:
        path = item["path"]
        actual = item["post_git_blob_sha1"]
        old = item["historical_post_git_blob_sha1"]
        if (not isinstance(path, str) or path in seen or
            not path.startswith(PRODUCT_PREFIXES) or
            chr(92) in path or ".." in path.split("/") or
            not isinstance(actual, str) or not HEX40.fullmatch(actual) or
            not isinstance(old, str) or not HEX40.fullmatch(old)):
            raise AssertionError("INVALID_P04_SOURCE_BINDING")
        seen.add(path)
        if git("rev-parse", head + ":" + path) != actual:
            raise AssertionError("PINNED_SOURCE_BLOB_MISMATCH")
        if item["status"] == "EXACT_HISTORICAL_MATCH":
            if actual != old:
                raise AssertionError("FALSE_HISTORICAL_MATCH")
            matches += 1
        elif item["status"] == "CURRENT_SOURCE_EVOLVED_REVIEW_REQUIRED":
            if actual == old:
                raise AssertionError("UNNECESSARY_DRIFT_STATUS")
            evolved += 1
        else:
            raise AssertionError("UNAUTHORIZED_SOURCE_STATUS")
    archival = record.get("historical_workflow", {})
    legacy_path = archival.get("path")
    if (legacy_path != ".github/workflows/nox-p04-candidate-ci.yml" or
        archival.get("integrate_into_product") is not False or
        archival.get("current_path_exists") is not False):
        raise AssertionError("HISTORICAL_CI_MISCLASSIFIED")
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e",
                       head + ":" + legacy_path], capture_output=True,
                      timeout=15).returncode == 0:
        raise AssertionError("HISTORICAL_WORKFLOW_ACTIVE_ON_PINNED_HEAD")
    return matches, evolved


class P04PinnedSourceReceiptTests(unittest.TestCase):
    def test_pinned_current_source_evidence_only(self):
        record = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(require_pinned_receipt(record), (3, 1))
        self.assertIs(record["constraints"]["source_presence_verified"], True)
        for forbidden in ("functional_source_verified", "same_head_native_windows",
                          "qa_accepted", "source_ready", "build_authorized"):
            self.assertIs(record["constraints"][forbidden], False)

    def test_rejects_forged_current_blob(self):
        record = json.loads(MANIFEST.read_text(encoding="utf-8"))
        record["files"][0]["post_git_blob_sha1"] = "0" * 40
        with self.assertRaisesRegex(AssertionError, "PINNED_SOURCE_BLOB_MISMATCH"):
            require_pinned_receipt(record)


if __name__ == "__main__":
    unittest.main()
