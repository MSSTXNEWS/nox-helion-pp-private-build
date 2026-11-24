"""B0 owner-exported proxy source wire evidence; never a dispatch authority.

Use an independently obtained expected SHA256. This is a lexical AST census,
not proof of a reachable SSE writer, installed code, or a compatible wire.
No imports/execution of the examined source and no secret literals in output.
"""
import ast
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

LIMIT = 2 * 1024 * 1024
TASK = "B0-R65-PINNED-PROXY-WIRE-STATIC-EVIDENCE-20261124"


def inspect(raw, expected):
    out = dict(task_id=TASK, decision="HOLD_SOURCE_UNVERIFIED",
               post_authorized=False, native_accepted=False)
    if (type(raw) is not bytes or len(raw) > LIMIT or
            type(expected) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected)):
        return out
    digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(digest, expected):
        return out
    out["source_sha256"] = digest
    try:
        root = ast.parse(raw)
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        out["decision"] = "HOLD_SOURCE_PARSE"
        return out
    counts = dict(data_prefix=0, id_prefix=0, named_delta=0,
                  dynamic_event_prefix=0, done_literal=0, token_literal=0)
    # Counts intentionally include unreachable code; no positive permission.
    for node in ast.walk(root):
        if not isinstance(node, ast.Constant) or type(node.value) is not str:
            continue
        value = node.value
        counts["data_prefix"] += bool(re.search(r"(?:^|\n)data:", value))
        counts["id_prefix"] += bool(re.search(r"(?:^|\n)id:", value))
        counts["named_delta"] += bool(re.search(r"(?:^|\n)event:[ \t]*delta(?:\n|$)", value))
        counts["dynamic_event_prefix"] += bool(re.search(r"(?:^|\n)event:[ \t]*$", value))
        counts["done_literal"] += value in ("[DONE]", "done")
        counts["token_literal"] += value == "token"
    out["literal_counts"] = counts
    out["decision"] = "HOLD_STATIC_ONLY_REQUIRE_OWNER_WIRE_WITNESS"
    return out


def selftest():
    fixtures = [
        (b'def stream():\n yield f"data: {x}\\n\\n"\nkind="token"\n', "data_prefix", 1),
        (b'def stream():\n yield f"id: {i}\\nevent: delta\\ndata: {x}\\n\\n"\n', "named_delta", 1),
        (b'def stream():\n yield f"event: {e}\\n"\n', "dynamic_event_prefix", 1),
    ]
    for raw, key, count in fixtures:
        result = inspect(raw, hashlib.sha256(raw).hexdigest())
        assert result["literal_counts"][key] == count, result
        assert not result["post_authorized"] and not result["native_accepted"]
    raw = b'password="DO_NOT_REPORT_SENTINEL"\n'
    result = inspect(raw, hashlib.sha256(raw).hexdigest())
    assert "DO_NOT_REPORT_SENTINEL" not in json.dumps(result)
    assert not result["post_authorized"]
    assert inspect(raw, "0" * 64)["decision"] == "HOLD_SOURCE_UNVERIFIED"
    raw = b"def broken("
    assert inspect(raw, hashlib.sha256(raw).hexdigest())["decision"] == "HOLD_SOURCE_PARSE"
    assert inspect(b"x" * (LIMIT + 1), "0" * 64)["decision"] == "HOLD_SOURCE_UNVERIFIED"
    assert inspect(b"x", None)["decision"] == "HOLD_SOURCE_UNVERIFIED"
    print("B0_R65_STATIC_SOURCE_EVIDENCE 8/8 SOURCE_ONLY NATIVE_ACCEPTED=false")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
    elif len(sys.argv) == 3:
        # Run only against an owner-exported copy, not a credential path.
        try:
            with Path(sys.argv[1]).open("rb") as handle:
                raw = handle.read(LIMIT + 1)
            result = inspect(raw, sys.argv[2])
        except OSError:
            result = dict(task_id=TASK, decision="HOLD_SOURCE_UNAVAILABLE",
                          post_authorized=False, native_accepted=False)
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(2)  # Static evidence never authorizes a request.
    else:
        raise SystemExit("usage: selftest OR OWNER_EXPORTED_PROXY.py EXPECTED_SHA256")
