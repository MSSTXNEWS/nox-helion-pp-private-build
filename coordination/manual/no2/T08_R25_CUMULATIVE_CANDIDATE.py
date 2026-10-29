"""NOX V16/T08: check evidence before claiming DONE; never execute a product patch.

This source-only gate does not run in the background or prove Windows runtime.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
STEPS = ("t06_accepted_source", "p0p1_same_head", "handoff_readback")
DOCS = ("Master", "E06", "Lessons")


def _sha(value, pattern=HEX40):
    return type(value) is str and pattern.fullmatch(value) is not None




def _root_git():
    import subprocess
    root = next(parent for parent in Path(__file__).resolve().parents
                if (parent / "coordination/e06/t06_closeout_guard.py").is_file())
    def git(*argv):
        result = subprocess.run(["git", "-C", str(root), *argv],
                                capture_output=True, timeout=12, check=False)
        if result.returncode:
            raise ValueError("GIT_OBJECT_READBACK_FAILED")
        return result.stdout
    return root, git


def _actual_json_blob(git, sha):
    if not _sha(sha) or git("cat-file", "-t", sha).strip() != b"blob":
        raise ValueError("GIT_RECEIPT_NOT_BLOB")
    if not 2 <= int(git("cat-file", "-s", sha).strip()) <= 262144:
        raise ValueError("GIT_RECEIPT_OUT_OF_BOUNDS")
    obj = json.loads(git("cat-file", "blob", sha))
    if type(obj) is not dict:
        raise ValueError("GIT_RECEIPT_NOT_JSON")
    return obj


def _verified_git_proof(source, t06):
    """Require Git HEAD/tree, manifest bytes and the existing T06 owner closeout guard."""
    import importlib.util
    import subprocess
    try:
        root, git = _root_git()
        if git("rev-parse", "HEAD").decode().strip() != source.get("head"):
            return False
        if git("rev-parse", "HEAD^{tree}").decode().strip() != source.get("tree"):
            return False
        owner = _actual_json_blob(git, t06.get("owner_receipt_blob"))
        if owner.get("head_sha") != source.get("head") or owner.get("tree_sha") != source.get("tree"):
            return False
        manifest_blob = owner.get("manifest_blob_sha")
        if not _sha(manifest_blob) or git("cat-file", "-t", manifest_blob).strip() != b"blob":
            return False
        if hashlib.sha256(git("cat-file", "blob", manifest_blob)).hexdigest() != source.get("manifest_sha256"):
            return False
        path = root / "coordination/e06/t06_closeout_guard.py"
        spec = importlib.util.spec_from_file_location("nox_t06_owner_gate", path)
        if not spec or not spec.loader:
            return False
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        verdict = guard.decide(owner, repo_root=root)
        return (verdict.get("done") is True and verdict.get("source_owner_accepted") is True
                and verdict.get("source_ready") is False)
    except (OSError, ValueError, KeyError, TypeError, StopIteration,
            ImportError, subprocess.TimeoutExpired, UnicodeError):
        return False


def _verified_downstream(source, p0, handoff, journal):
    """Reject forged downstream hashes; T02 must separately verify native Drive revisions."""
    import subprocess
    try:
        _, git = _root_git()
        head = source.get("head")
        if git("rev-parse", "HEAD").decode().strip() != head:
            return False
        for part in (p0, handoff):
            proof = _actual_json_blob(git, part.get("receipt_blob"))
            # All declared source identities must agree, not just one alias.
            claims = [proof[k] for k in
                      ("head", "head_sha", "source_head", "source_head_sha")
                      if k in proof]
            if not claims or any(type(x) is not str or x != head for x in claims):
                return False
        if p0.get("status") == "PATCH_APPLIED":
            test = _actual_json_blob(git, p0.get("focused_test_blob"))
            if test.get("status") != "PASS":
                return False
            # A PASS for a different HEAD cannot authorize this source.
            test_heads = [test[k] for k in
                          ("head", "head_sha", "source_head", "source_head_sha")
                          if k in test]
            if not test_heads or any(type(x) is not str or x != head
                                     for x in test_heads):
                return False
        for name in DOCS:
            doc = journal[name]
            proof = _actual_json_blob(git, doc.get("readback_receipt_blob"))
            if (proof.get("doc") != name or
                    proof.get("revision_id") != doc.get("revision_id") or
                    proof.get("incident_id") != doc.get("incident_id") or
                    proof.get("readback_pass") is not True):
                return False
        return git("rev-parse", "HEAD").decode().strip() == head
    except (OSError, ValueError, KeyError, TypeError, StopIteration,
            subprocess.TimeoutExpired, UnicodeError):
        return False

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
    downstream = (ready and type(p0) is dict and type(handoff) is dict
                  and type(journal) is dict and _verified_downstream(source, p0, handoff, journal))
    disposition = downstream and (
        p0.get("head") == target and p0.get("status") in
        ("NO_CODE_BLOCKERS", "PATCH_APPLIED") and _sha(p0.get("receipt_blob"))
        and (p0.get("status") != "PATCH_APPLIED" or _sha(p0.get("focused_test_blob"))))
    docs = (type(journal) is dict and all(
        type(journal.get(name)) is dict and
        journal[name].get("incident_id") == receipt["incident_id"] and
        type(journal[name].get("revision_id")) is str and
        len(journal[name]["revision_id"]) >= 8 and
        journal[name].get("readback_pass") is True for name in DOCS))
    delivered = disposition and docs and type(handoff) is dict and (
        handoff.get("head") == target and
        handoff.get("t09_t10_delivered") is True and
        handoff.get("comment_readback_pass") is True and
        _sha(handoff.get("receipt_blob")))
    values = (bool(ready), bool(disposition), bool(delivered))
    count = sum(values)
    return {"schema": "NOX_V16_T08_AUTOFIX_CLOSEOUT_GATE_V1",
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
