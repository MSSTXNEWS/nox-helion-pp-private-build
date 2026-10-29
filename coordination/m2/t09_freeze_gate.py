"""NOX V16 M2/T09: independent source-only, fail-closed freeze eligibility gate.

Not a freezer: a T09 immutable receipt is created only after all source gates PASS.
No build, network access, product mutation, or E07 acceptance.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _git(repo: Path, *args: str) -> bytes:
    output = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, check=False, timeout=12,
    )
    if output.returncode:
        raise ValueError("GIT_OBJECT_READBACK_FAILED")
    return output.stdout


def _object_json(repo: Path, sha: str) -> dict:
    if not isinstance(sha, str) or not GIT_SHA.fullmatch(sha):
        raise ValueError("GIT_BLOB_SHA_REQUIRED")
    if _git(repo, "cat-file", "-t", sha).strip() != b"blob":
        raise ValueError("EVIDENCE_NOT_A_GIT_BLOB")
    raw = _git(repo, "cat-file", "blob", sha)
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("EVIDENCE_NOT_JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("EVIDENCE_NOT_AN_OBJECT")
    return result


def evaluate(repo: str | Path, evidence: dict) -> dict:
    """Check T06 + T08 + T07 bytes and same HEAD; never claim frozen itself."""
    root = Path(repo).resolve()
    source = evidence.get("source", {}) if isinstance(evidence, dict) else {}
    head = source.get("head") if isinstance(source, dict) else None
    tree = source.get("tree") if isinstance(source, dict) else None
    manifest_blob = source.get("manifest_blob") if isinstance(source, dict) else None

    def hold(reason: str) -> dict:
        return {"status": "FREEZE_HOLD", "reason": reason, "head": head, "frozen": False}

    if not all(isinstance(s, str) and GIT_SHA.fullmatch(s)
               for s in (head, tree, manifest_blob)):
        return hold("VALID_HEAD_TREE_MANIFEST_REQUIRED")
    if not isinstance(evidence, dict):
        return hold("EVIDENCE_DICT_REQUIRED")
    try:
        if (_git(root, "rev-parse", "HEAD").decode().strip() != head or
                _git(root, "rev-parse", "HEAD^{tree}").decode().strip() != tree):
            return hold("CURRENT_HEAD_TREE_DRIFT")
        manifest = _object_json(root, manifest_blob)
        if (manifest.get("head_sha") != head or
                manifest.get("tree_sha") != tree or
                manifest.get("owner_acceptance") is not True):
            return hold("OWNER_ACCEPTED_MANIFEST_REQUIRED")
        expected_manifest_hash = evidence.get("manifest_sha256")
        if (not isinstance(expected_manifest_hash, str) or
                not SHA256.fullmatch(expected_manifest_hash) or
                hashlib.sha256(_git(root, "cat-file", "blob", manifest_blob)).hexdigest()
                != expected_manifest_hash):
            return hold("MANIFEST_RAW_SHA256_MISMATCH")

        t06_blob = evidence.get("t06_receipt_blob")
        t06 = _object_json(root, t06_blob)
        if (t06.get("head_sha") != head or t06.get("tree_sha") != tree or
                t06.get("manifest_blob_sha") != manifest_blob or
                t06.get("owner_acceptance") is not True or
                t06.get("source_no_loss_attested") is not True or
                not isinstance(t06.get("criteria"), dict) or
                len(t06["criteria"]) != 8):
            return hold("T06_SAME_HEAD_8_CRITERIA_RECEIPT_REQUIRED")

        # Reuse the actual existing T06 gate; do not add a second owner policy.
        import importlib.util
        guard_path = root / "coordination/e06/t06_closeout_guard.py"
        if not guard_path.is_file() or guard_path.is_symlink():
            return hold("OFFICIAL_T06_SOURCE_GATE_MISSING")
        # Import exactly the Git-tracked bytes; never execute an altered working
        # tree file or a stale/poisoned __pycache__ instead of the accepted HEAD.
        guard_rel = "coordination/e06/t06_closeout_guard.py"
        guard_bytes = guard_path.read_bytes()
        expected = _git(root, "rev-parse", "HEAD:" + guard_rel).decode().strip()
        current = subprocess.run(
            ["git", "-C", str(root), "hash-object", "--path", guard_rel, "--stdin"],
            input=guard_bytes, capture_output=True, check=False, timeout=12,
        )
        if current.returncode or current.stdout.decode().strip() != expected:
            return hold("T06_GUARD_WORKTREE_DRIFT")
        import types
        mod = types.ModuleType("nox_m2_official_t06")
        mod.__file__ = str(guard_path)
        exec(compile(guard_bytes, str(guard_path), "exec"), mod.__dict__)
        t06_result = mod.decide(t06, repo_root=root)
        if t06_result.get("done") is not True or t06_result.get("source_owner_accepted") is not True:
            return hold("T06_OWNER_GATE_NOT_8_OF_8")

        t08 = _object_json(root, evidence.get("t08_receipt_blob"))
        if (t08.get("head") != head or t08.get("tree") != tree or
                t08.get("manifest_blob") != manifest_blob or
                t08.get("status") not in ("NO_CODE_BLOCKERS", "PATCH_APPLIED") or
                t08.get("independent_verifier") == t06.get("run_id") or
                not isinstance(t08.get("independent_verifier"), str) or
                len(t08["independent_verifier"]) < 8 or
                not isinstance(t08.get("run_id"), str) or
                len(t08["run_id"]) < 8):
            return hold("INDEPENDENT_T08_SAME_HEAD_DISPOSITION_REQUIRED")
        # A patch needs an exact test receipt, not an unverified PATCH_APPLIED note.
        if t08["status"] == "PATCH_APPLIED":
            tested = _object_json(root, t08.get("focused_test_receipt_blob"))
            if (tested.get("head") != head or tested.get("status") != "PASS" or
                    tested.get("source_run_id") != t08["run_id"]):
                return hold("T08_PATCH_INDEPENDENT_TEST_UNVERIFIED")

        original = _object_json(root, evidence.get("original_lock_receipt_blob"))
        if (original.get("original_zip_sha256") !=
                "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a" or
                original.get("members_verified") != 729 or
                original.get("status") != "PASS"):
            return hold("ORIGINAL_729_SOURCELOCK_PROVENANCE_MISSING")

        return {"status": "ELIGIBLE_FOR_T09_IMMUTABLE_RECEIPT", "head": head,
                "tree": tree, "manifest_blob": manifest_blob,
                "manifest_sha256": expected_manifest_hash, "frozen": False,
                "t10_required_before_freeze": False}
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            subprocess.TimeoutExpired, ImportError, AttributeError):
        return hold("GIT_OR_OWNER_RECEIPT_READBACK_FAILED")
