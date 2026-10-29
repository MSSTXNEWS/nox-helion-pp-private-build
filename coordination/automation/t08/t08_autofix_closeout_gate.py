"""NOX V16/T08: check evidence before claiming DONE; never execute a product patch.

This source-only gate does not run in the background or prove Windows runtime.
"""
import argparse
import json
import re
from pathlib import Path

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
STEPS = ("t06_accepted_source", "p0p1_same_head", "handoff_readback")
DOCS = ("Master", "E06", "Lessons")


def _sha(value, pattern=HEX40):
    return type(value) is str and pattern.fullmatch(value) is not None



def _verified_git_proof(source, t06):
    """Fail closed: a SHA-shaped string is never owner/source acceptance."""
    import hashlib
    import subprocess

    try:
        root = next(p for p in Path(__file__).resolve().parents
                    if (p / "coordination/e06/t06_closeout_guard.py").is_file())

        def git(*args):
            response = subprocess.run(["git", "-C", str(root), *args],
                                      check=False, capture_output=True,
                                      timeout=12)
            if response.returncode:
                raise ValueError("GIT_EVIDENCE_NOT_READABLE")
            return response.stdout

        head = git("rev-parse", "HEAD").decode("ascii").strip()
        tree = git("rev-parse", "HEAD^{tree}").decode("ascii").strip()
        if head != source["head"] or tree != source["tree"]:
            return False
        owner_blob_sha = t06.get("owner_receipt_blob")
        if not _sha(owner_blob_sha) or git("cat-file", "-t", owner_blob_sha).strip() != b"blob":
            return False
        owner_receipt = json.loads(git("cat-file", "blob", owner_blob_sha))
        if any(owner_receipt.get(k) != source[s] for k, s in
               (("head_sha", "head"), ("tree_sha", "tree"))):
            return False
        manifest_blob = owner_receipt.get("manifest_blob_sha")
        if not _sha(manifest_blob) or git("cat-file", "-t", manifest_blob).strip() != b"blob":
            return False
        if hashlib.sha256(git("cat-file", "blob", manifest_blob)).hexdigest() != source["manifest_sha256"]:
            return False

        guard = root / "coordination/e06/t06_closeout_guard.py"
        if not guard.is_file() or guard.is_symlink():
            return False
        # Commit-pinned bytes: worktree modifications and __pycache__ cannot forge PASS.
        rel = "coordination/e06/t06_closeout_guard.py"
        guard_bytes = guard.read_bytes()
        expected = git("rev-parse", "HEAD:" + rel).decode("ascii").strip()
        actual = subprocess.run(
            ["git", "-C", str(root), "hash-object", "--path", rel, "--stdin"],
            input=guard_bytes, capture_output=True, check=False, timeout=12)
        if actual.returncode or actual.stdout.decode("ascii").strip() != expected:
            return False
        import types
        module = types.ModuleType("_nox_m2_t06_guard")
        module.__file__ = str(guard)
        exec(compile(guard_bytes, str(guard), "exec"), module.__dict__)
        verdict = module.decide(owner_receipt, repo_root=root)
        return verdict.get("done") is True and verdict.get("source_owner_accepted") is True
    except (OSError, ValueError, KeyError, TypeError, StopIteration,
            ImportError, subprocess.TimeoutExpired, UnicodeError):
        return False

def _bound_receipt(repo, sha, head, status=None):
    """Verify existence and source identity of receipts, not their SHA-shaped text."""
    import subprocess
    if not _sha(sha):
        return False
    try:
        def git(*args):
            p = subprocess.run(["git", "-C", str(repo), *args],
                               capture_output=True, timeout=12, check=False)
            if p.returncode: raise ValueError("GIT_EVIDENCE_UNREADABLE")
            return p.stdout
        if git("cat-file", "-t", sha).strip() != b"blob":
            return False
        data = json.loads(git("cat-file", "blob", sha))
        return (type(data) is dict and
                (data.get("head") == head or data.get("source_head") == head) and
                (status is None or data.get("status") == status) and
                type(data.get("run_id")) is str and len(data["run_id"]) >= 8)
    except (ValueError, TypeError, UnicodeError, OSError, subprocess.TimeoutExpired):
        return False

def _source_repo():
    try:
        return next(p for p in Path(__file__).resolve().parents
                    if (p / "coordination/e06/t06_closeout_guard.py").is_file())
    except StopIteration:
        return None


def decide(receipt):
    if type(receipt) is not dict or type(receipt.get("incident_id")) is not str:
        raise ValueError("UNIQUE_ERROR_INCIDENT_REQUIRED")
    source = receipt.get("source", {})
    t06 = receipt.get("t06", {})
    p0 = receipt.get("p0p1", {})
    handoff = receipt.get("handoff", {})
    journal = receipt.get("journal", {})
    target = source.get("head") if type(source) is dict else None
    tree = source.get("tree") if type(source) is dict else None
    manifest = source.get("manifest_sha256") if type(source) is dict else None
    pinned = _sha(target) and _sha(tree) and _sha(manifest, HEX64)
    ready = pinned and type(t06) is dict and _verified_git_proof(source, t06) and (
        t06.get("accepted") is True and t06.get("head") == target
        and t06.get("tree") == tree and t06.get("manifest_sha256") == manifest
        and _sha(t06.get("owner_receipt_blob"))
        and t06.get("p01_p05_accepted") is True
        and t06.get("host50_native_contracts_verified") is True)
    root = _source_repo()
    disposition = ready and root is not None and type(p0) is dict and (
        p0.get("head") == target and p0.get("status") in
        ("NO_CODE_BLOCKERS", "PATCH_APPLIED") and
        _bound_receipt(root, p0.get("receipt_blob"), target, p0.get("status")) and
        (p0.get("status") != "PATCH_APPLIED" or
         _bound_receipt(root, p0.get("focused_test_blob"), target, "PASS")))
    docs = (type(journal) is dict and all(
        type(journal.get(name)) is dict and
        journal[name].get("incident_id") == receipt["incident_id"] and
        type(journal[name].get("revision_id")) is str and
        len(journal[name]["revision_id"]) >= 8 and
        journal[name].get("readback_pass") is True for name in DOCS))
    docs = docs and root is not None and _bound_receipt(
        root, journal.get("t02_readback_receipt_blob"), target, "PASS")
    delivered = disposition and docs and type(handoff) is dict and (
        handoff.get("head") == target and
        handoff.get("t09_t10_delivered") is True and
        handoff.get("comment_readback_pass") is True and
        _bound_receipt(root, handoff.get("receipt_blob"), target))
    values = (bool(ready), bool(disposition), bool(delivered))
    count = sum(values)
    return {"schema": "NOX_V16_T08_GIT_EVIDENCE_R02",
            "incident_id": receipt["incident_id"],
            "status": "DONE" if count == 3 else "HOLD_EVIDENCE",
            "progress": f"{count}/3", "percentage": round(count * 100 / 3, 1),
            "bar": "█" * round(10 * count / 3) + "░" * (10-round(10*count/3)),
            "criteria": dict(zip(STEPS, values)),
            "missing": [k for k, v in zip(STEPS, values) if not v],
            "premature_done_rejected": receipt.get("claimed_status") in
                ("DONE", "SOURCE_READY", "100%") and count != 3,
            "warning": "No code execution/native Windows QA or source acceptance is implied."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    print(json.dumps(decide(json.loads(args.receipt.read_text(encoding="utf-8"))),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
