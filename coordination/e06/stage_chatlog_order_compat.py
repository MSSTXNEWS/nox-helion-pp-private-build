#!/usr/bin/env python3
"""E06 stage-only R11 UI bridge repair: chatLog TDZ; original owner files unchanged.

The historical R11 Assets/index.html attaches three chatLog listeners before its
const chatLog binding. This is a real Chromium pageerror in an archived source,
not a verified installed app defect. Fail closed on any byte drift.
"""
from __future__ import annotations
import argparse, hashlib, difflib, json, pathlib, sys

APPROVED_SHA256 = "3a8e027ed98ba5fbcae6e047b2d559ba9ac8c5270fb1be36b1379ee226ad2a76"
DECL_BEGIN = "const chatModel=document.getElementById('chat-model'),chatLog="
DECL_END = ";let chatId=sessionStorage.getItem('nox-chat-id')"
BEFORE = "let chatScrollFrame=0;function cancelScheduledChatScroll()"

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def transform(raw: bytes) -> tuple[bytes, bytes]:
    if sha(raw) != APPROVED_SHA256:
        raise ValueError("APPROVED_R11_HTML_SHA_PREIMAGE_HOLD")
    old = raw.decode("utf-8")
    if any(old.count(x) != 1 for x in (DECL_BEGIN, DECL_END, BEFORE)):
        raise ValueError("CHATLOG_DECLARATION_OR_UI_ANCHOR_DRIFT")
    start = old.index(DECL_BEGIN)
    end = old.index(DECL_END, start)
    segment = old[start:end + 1]
    anchor = old.index(BEFORE)
    if not (anchor < start and "chatLog.addEventListener" in old[anchor:start]):
        raise ValueError("NO_PREINIT_CHATLOG_BUG_OR_ALREADY_FIXED")
    stripped = old[:start] + old[end+1:]
    pos = stripped.index(BEFORE)
    result = stripped[:pos] + segment + "\n" + stripped[pos:]
    if result.count(DECL_BEGIN) != 1 or result.count("chatLog.addEventListener") != 3:
        raise ValueError("NO_LOSS_UI_LISTENER_PRESERVATION_HOLD")
    if result.replace(segment + "\n", "", 1) != old.replace(segment, "", 1):
        raise ValueError("NO_LOSS_MOVE_ONLY_HOLD")
    patch = "".join(difflib.unified_diff(
        old.splitlines(True), result.splitlines(True),
        fromfile="approved-R11/Assets/index.html",
        tofile="stage-only-R11/Assets/index.html",
    )).encode("utf-8")
    return result.encode("utf-8"), patch

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=pathlib.Path, required=True)
    ap.add_argument("--receipt", type=pathlib.Path, required=True)
    args = ap.parse_args()
    stage = args.stage.resolve()
    item = stage / "Assets" / "index.html"
    previous = args.receipt.with_name("R11-approved-index.html.original")
    diff = args.receipt.with_suffix(".patch")
    if not item.is_file() or item.is_symlink() or any(p.exists() or p.is_symlink() for p in (args.receipt, previous, diff)):
        raise SystemExit("OWNER_SOURCE_OR_STAGING_OUTPUT_CONFLICT")
    original = item.read_bytes()
    try:
        updated, patch = transform(original)
    except ValueError as exc:
        raise SystemExit(str(exc))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with previous.open("xb") as handle:
        handle.write(original)
    with diff.open("xb") as handle:
        handle.write(patch)
    item.write_bytes(updated)   # temporary disposable CI stage only
    data = {
        "schema": "NOX_E06_ORIGINAL_CHATLOG_STAGE_V1",
        "owner": 6,
        "source_owner": 1,
        "pre_sha256": sha(original),
        "post_sha256": sha(updated),
        "unified_patch_sha256": sha(patch),
        "original_copy_sha256": sha(previous.read_bytes()),
        "stage_only": True,
        "owner_source_unchanged": True,
        "ui_handlers_removed": 0,
        "native_windows_verified": False,
        "release_accepted": False,
        "rollback": "Restore R11-approved-index.html.original to disposable staged Assets/index.html"
    }
    with args.receipt.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    if sha(item.read_bytes()) != sha(updated):
        raise SystemExit("STAGED_CHATLOG_BYTE_READBACK_HOLD")
    print("NOX_E06_STAGED_CHATLOG_INIT_ORDER_COMPAT_PASS_NOT_E07", data["post_sha256"])
    return 0

if __name__ == "__main__":
    sys.exit(main())
