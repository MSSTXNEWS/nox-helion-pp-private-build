"""T06 source-owner closeout gate. Never substitutes for T10 SOURCE_READY.

Every accepted item must point to Git-readable, owner-bound source/test receipts.
The official T06 exit is run_source_integrations_r13.py --t06-closeout <json>.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

CRITERIA = ("base", "P01", "P02", "P03", "P04", "P05",
            "common_integration", "accepted_head_manifest")
OWNER_ID = {"P01": 1, "P02": 2, "P03": 3, "P04": 4, "P05": 5,
            "common_integration": 6, "accepted_head_manifest": 6}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z")
PROOF = ("owner_receipt", "preimage_sha", "postimage_sha", "test_receipt")


def _sha(value, length=40):
    return isinstance(value, str) and bool((HEX40 if length == 40 else HEX64).fullmatch(value))


def _path(value):
    return (isinstance(value, str) and bool(value) and not value.startswith("/")
            and "\\" not in value and "\x00" not in value
            and all(p not in ("", ".", "..") for p in value.split("/")))


class GitReadback:
    """Read-only verification against the actual local checkout, not claimed strings."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.root), *args],
                           capture_output=True, timeout=12, check=False)
        if p.returncode:
            raise ValueError("GIT_READBACK_FAILED:" + " ".join(args[:2]))
        return p.stdout

    def obj(self, sha, kind):
        if not _sha(sha):
            raise ValueError("INVALID_GIT_SHA")
        if self.git("cat-file", "-t", sha).decode().strip() != kind:
            raise ValueError("WRONG_GIT_OBJECT_TYPE")
        return self.git("cat-file", "-p", sha)

    def blob(self, sha):
        return self.obj(sha, "blob")

    def source_blob(self, ref, path):
        if not _path(path):
            raise ValueError("UNSAFE_SOURCE_PATH")
        raw = self.git("rev-parse", ref + ":" + path).decode().strip()
        if not _sha(raw):
            raise ValueError("SOURCE_BLOB_NOT_GIT_SHA")
        return raw

    def digest(self, sha, claimed):
        data = self.blob(sha)
        if _sha(claimed):
            return sha == claimed
        return _sha(claimed, 64) and hashlib.sha256(data).hexdigest() == claimed

    def owner_and_test(self, name, row):
        ev = row.get("evidence")
        if not isinstance(ev, dict) or set(PROOF) - set(ev):
            return False
        if type(row.get("owner_id")) is not int or row["owner_id"] != OWNER_ID[name]:
            return False
        path = ev.get("source_path")
        owner, test = ev["owner_receipt"], ev["test_receipt"]
        if not _path(path) or not isinstance(owner, dict) or not isinstance(test, dict):
            return False
        if not all(_sha(x.get("blob_sha")) and isinstance(x.get("run_id"), str)
                   and RUN.fullmatch(x["run_id"]) for x in (owner, test)):
            return False
        pre, post = ev["preimage_sha"], ev["postimage_sha"]
        pre_blob = ev.get("preimage_blob_sha", pre if _sha(pre) else None)
        post_blob = ev.get("postimage_blob_sha", post if _sha(post) else None)
        if not all(_sha(b) for b in (pre_blob, post_blob)):
            return False
        if not self.digest(pre_blob, pre) or not self.digest(post_blob, post):
            return False
        if self.source_blob("HEAD", path) != post_blob:
            return False
        try:
            owner_data = json.loads(self.blob(owner["blob_sha"]))
            test_data = json.loads(self.blob(test["blob_sha"]))
        except (ValueError, UnicodeError, TypeError):
            return False
        return (isinstance(owner_data, dict) and isinstance(test_data, dict)
                and owner_data.get("owner_id") == row["owner_id"]
                and owner_data.get("run_id") == owner["run_id"]
                and owner_data.get("source_path") == path
                and owner_data.get("preimage_sha") == pre
                and owner_data.get("postimage_sha") == post
                and owner_data.get("approved") is True
                and test_data.get("run_id") == test["run_id"]
                and test_data.get("owner_run_id") == owner["run_id"]
                and test_data.get("source_path") == path
                and test_data.get("postimage_sha") == post
                and test_data.get("status") == "PASS")

    def base(self, ev):
        if not isinstance(ev, dict):
            return False
        head = ev.get("canonical_head_sha")
        choice = ev.get("source_choice_receipt")
        if not _sha(head) or not _sha(choice):
            return False
        self.obj(head, "commit")
        self.blob(choice)
        self.git("merge-base", "--is-ancestor", head, "HEAD")
        return True

    def manifest(self, receipt):
        # T06 signs the owner source state; T09 freezes it and T10 checks later.
        handoff = receipt.get("handoff_to_t09")
        if (receipt.get("source_no_loss_attested") is not True
                or not isinstance(handoff, dict)):
            return False
        for key in ("owner_acceptance_receipt_sha", "no_loss_receipt_sha"):
            self.blob(receipt.get(key))
        self.blob(handoff.get("receipt_sha"))
        if any(handoff.get(key) != receipt.get(key)
               for key in ("head_sha", "tree_sha", "manifest_blob_sha")):
            return False
        head = receipt.get("head_sha")
        tree = receipt.get("tree_sha")
        blob = receipt.get("manifest_blob_sha")
        if not all(_sha(s) for s in (head, tree, blob)):
            return False
        self.obj(head, "commit")
        self.obj(tree, "tree")
        if self.git("rev-parse", "HEAD").decode().strip() != head:
            return False
        if self.git("rev-parse", "HEAD^{tree}").decode().strip() != tree:
            return False
        try:
            manifest = json.loads(self.blob(blob))
        except (ValueError, UnicodeError, TypeError):
            return False
        return (isinstance(manifest, dict)
                and manifest.get("head_sha") == head
                and manifest.get("tree_sha") == tree
                and manifest.get("owner_acceptance") is True)


def decide(receipt: dict, repo_root=None) -> dict:
    if not isinstance(receipt, dict) or not isinstance(receipt.get("criteria"), dict):
        raise ValueError("FIXED_T06_CRITERIA_MISSING")
    if set(receipt["criteria"]) != set(CRITERIA):
        raise ValueError("T06_MUST_HAVE_EXACTLY_EIGHT_CRITERIA")
    run_id = receipt.get("run_id")
    if not isinstance(run_id, str) or not run_id.startswith("NOX-V16-T06-") or not RUN.fullmatch(run_id):
        raise ValueError("INVALID_T06_RUN_ID")
    verifier = GitReadback(repo_root or Path(__file__).resolve().parents[2])
    accepted, remaining, used_receipts = [], [], set()
    for name in CRITERIA:
        row = receipt["criteria"][name]
        if not isinstance(row, dict):
            raise ValueError("INVALID_CRITERION_" + name)
        ok = False
        if row.get("status") == "DONE":
            try:
                if name == "base":
                    ok = verifier.base(row.get("evidence"))
                else:
                    ok = verifier.owner_and_test(name, row)
                    if ok:
                        evidence = row["evidence"]
                        receipt_pair = (evidence["owner_receipt"]["blob_sha"],
                                        evidence["test_receipt"]["blob_sha"])
                        if any(item in used_receipts for item in receipt_pair):
                            ok = False
                        else:
                            used_receipts.update(receipt_pair)
                    if name == "accepted_head_manifest" and ok:
                        ok = (receipt.get("owner_acceptance") is True
                              and verifier.manifest(receipt))
            except (ValueError, OSError, subprocess.TimeoutExpired):
                ok = False
        if ok:
            accepted.append(name)
        else:
            remaining.append({"criterion": name,
                              "owner": row.get("owner", "UNASSIGNED"),
                              "action": row.get("next_action", "OWNER_PRE_POST_TEST_GIT_READBACK")})
    count = len(accepted)
    done = count == 8
    segments = round(count * 10 / 8)
    return {"schema": "NOX_V16_T06_CLOSEOUT_GATE_V2",
            "run_id": run_id, "status": "OWNER_SOURCE_ACCEPTED" if done else "HOLD_INCOMPLETE",
            "done": done, "source_owner_accepted": done,
            "source_ready": False, "independent_source_qa": "T10_LATER",
            "premature_closeout_rejected": not done and receipt.get("claimed_status") in
                ("DONE", "COMPLETE", "SOURCE_READY", "100%"),
            "completed": count, "total": 8, "progress_pct": count * 12.5,
            "progress_bar": "█" * segments + "░" * (10 - segments),
            "remaining": remaining, "continuation_required": not done,
            "limitations": "Git evidence is necessary, not native Windows acceptance or T10 SOURCE_READY"}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="T06 SOURCE ONLY exit; fail-closed Git evidence")
    p.add_argument("receipt", type=Path)
    p.add_argument("--repo-root", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    out = decide(json.loads(a.receipt.read_text(encoding="utf-8")), a.repo_root)
    result = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    if a.output:
        if a.output.exists():
            raise RuntimeError("IMMUTABLE_GATE_RECEIPT_ALREADY_EXISTS")
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(result, encoding="utf-8")
    print(result, end="")
    return 0 if out["done"] else 2


if __name__ == "__main__":
    sys.exit(main())
