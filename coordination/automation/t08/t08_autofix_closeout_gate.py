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
    ready = pinned and type(t06) is dict and (
        t06.get("accepted") is True and t06.get("head") == target
        and t06.get("tree") == tree and t06.get("manifest_sha256") == manifest
        and _sha(t06.get("owner_receipt_blob"))
        and t06.get("p01_p05_accepted") is True
        and t06.get("host50_native_contracts_verified") is True)
    disposition = ready and type(p0) is dict and (
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
