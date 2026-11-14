"""Physical Windows Qwen probe for an already-built NOX installer.
Never treats provider generation or idle STOP as installed NOX E07 acceptance.
Uses the installed ORIGINAL OneHost native framed endpoint, not a second backend.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time
from urllib.request import Request, urlopen

MODEL = "qwen2.5-coder:1.5b"
MODEL_DIGEST_PREFIX = "d7372fd82851"
API = "http://127.0.0.1:11434"
PROTO = "NOX-P02-NATIVE-v1"


def get_json(path: str) -> object:
    with urlopen(API + path, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError("OLLAMA_HTTP_STATUS_HOLD")
        return json.loads(response.read(2_000_000).decode("utf-8"))


def provider_stream(prompt: str, *, limit: int, early_cancel: bool = False) -> dict:
    request = Request(
        API + "/api/chat",
        data=json.dumps({
            "model": MODEL, "messages": [{"role": "user", "content": prompt}],
            "stream": True, "options": {"num_predict": limit, "temperature": 0}
        }, separators=(",", ":")).encode("utf-8"),
        method="POST", headers={"Content-Type": "application/json"},
    )
    pieces = 0
    bytes_seen = 0
    complete = False
    aborted = False
    with urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError("QWEN_GENERATE_HTTP_HOLD")
        started = time.monotonic()
        while time.monotonic() - started < 110:
            raw = response.readline()
            if not raw:
                break
            if len(raw) > 1_000_000:
                raise RuntimeError("QWEN_STREAM_FRAME_OVERSIZE")
            row = json.loads(raw.decode("utf-8"))
            if row.get("error"):
                raise RuntimeError("QWEN_PROVIDER_STREAM_ERROR")
            message = row.get("message") or {}
            text = message.get("content", "")
            if isinstance(text, str) and text:
                pieces += 1
                bytes_seen += len(text.encode("utf-8"))
            if row.get("done") is True:
                complete = True
                break
            if early_cancel and pieces >= 2:
                # Closing an HTTP stream proves provider-side abort only.
                # It is NOT proof that the NOX native STOP route works.
                aborted = True
                break
    return {"nonempty_chunks": pieces, "generated_utf8_bytes": bytes_seen,
            "done": complete, "http_stream_closed_early": aborted}


def native_request(binary: Path, data_dir: Path, route: str,
                   payload: dict, index: int) -> dict:
    run_id = "NOX-QWEN-E07-" + str(index)
    nonce = f"{index:032x}"
    request = {"protocol": PROTO, "runId": run_id,
               "requestId": nonce, "route": route, "payload": payload}
    raw = json.dumps(request, separators=(",", ":")).encode("utf-8")
    result = subprocess.run(
        [str(binary), "--native-stdio", "--run-id", run_id,
         "--data-dir", str(data_dir)],
        input=struct.pack(">I", len(raw)) + raw, capture_output=True,
        timeout=180, cwd=binary.parent, check=False,
    )
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("NOX_INSTALLED_NATIVE_PROCESS_HOLD")
    frames = []
    pos = 0
    while pos < len(result.stdout):
        if len(result.stdout) - pos < 4:
            raise RuntimeError("NOX_NATIVE_FRAME_LENGTH_HOLD")
        size = struct.unpack(">I", result.stdout[pos:pos + 4])[0]
        pos += 4
        if not 1 <= size <= 1_048_576 or pos + size > len(result.stdout):
            raise RuntimeError("NOX_NATIVE_FRAME_BOUNDS_HOLD")
        frame = json.loads(result.stdout[pos:pos + size].decode("utf-8"))
        pos += size
        if (not isinstance(frame, dict)
                or any(frame.get(k) != request[k]
                       for k in ("protocol", "runId", "requestId"))):
            raise RuntimeError("NOX_NATIVE_IDENTITY_HOLD")
        frames.append(frame)
    if not frames:
        raise RuntimeError("NOX_NATIVE_EMPTY_REPLY_HOLD")
    # Never claim success from transport status alone.
    return {"status": frames[-1].get("status"),
            "errorCode": frames[-1].get("errorCode"),
            "results": [f.get("result") for f in frames],
            "frame_count": len(frames)}


def nonempty_response_text(reply: dict) -> int:
    texts = []
    for result in reply.get("results", []):
        if not isinstance(result, dict):
            continue
        for key in ("text", "answer", "response", "content", "delta"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value)
        for entry in result.get("events", []) if isinstance(result.get("events"), list) else []:
            if isinstance(entry, dict) and entry.get("type") == "chat.delta":
                value = entry.get("delta")
                if isinstance(value, str) and value.strip():
                    texts.append(value)
    return sum(len(x.encode("utf-8")) for x in texts)


def verify_installed_model_oci_bytes(reported_digest: str) -> dict:
    """Reuse the existing reviewed offline OCI verifier; never trust /api/tags alone.

    The approved Qwen manifest and EVERY config/layer byte must hash correctly,
    from the exact models directory used by Ollama. Read-only, no downloads,
    no privilege escalation, and no model / GUI / E07 success inferred.
    """
    script = Path(__file__).with_name("verify_qwen_oci_integrity.py")
    if (not script.is_file() or script.is_symlink() or
            getattr(script, "is_junction", lambda: False)()):
        raise RuntimeError("QWEN_OCI_REVIEWED_VERIFIER_MISSING_HOLD")
    spec = importlib.util.spec_from_file_location("nox_e07_reviewed_oci_bytes", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("QWEN_OCI_REVIEWED_VERIFIER_IMPORT_HOLD")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if reported_digest != module.APPROVED_MANIFEST_SHA256:
        raise RuntimeError("QWEN_OCI_FULL_MANIFEST_DIGEST_MISMATCH_HOLD")
    supplied = os.environ.get("OLLAMA_MODELS")
    if supplied is not None and (not supplied.strip() or
                                 not Path(supplied).is_absolute()):
        raise RuntimeError("QWEN_OCI_MODEL_ROOT_NOT_ABSOLUTE_HOLD")
    root = Path(supplied) if supplied is not None else Path.home() / ".ollama" / "models"
    # Do not resolve() before checking user-supplied Ollama model-root provenance.
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)()
           for p in (root, *root.parents)):
        raise RuntimeError("QWEN_OCI_MODEL_ROOT_REPARSE_HOLD")
    try:
        evidence = module.verify(root, reported_digest)
    except module.IntegrityHold as exc:
        raise RuntimeError("QWEN_" + str(exc)) from None
    if (evidence.get("schema") != "nox.qwen.oci.bytes.v1" or
            evidence.get("manifest_sha256") != reported_digest or
            evidence.get("independent_weights_sha_verified") is not True or
            type(evidence.get("verified_blobs")) is not int or
            evidence["verified_blobs"] < 2 or
            type(evidence.get("verified_blob_bytes")) is not int or
            evidence["verified_blob_bytes"] < 986048576 or
            evidence.get("release_accepted") is not False):
        raise RuntimeError("QWEN_OCI_PHYSICAL_EVIDENCE_INCOMPLETE_HOLD")
    return evidence


def qwen_probe_exit_code(report: dict) -> int:
    """History must survive a fresh native process before a Qwen probe succeeds."""
    return (0 if (report.get("installed_native") == "LIVE_NONEMPTY_RESPONSE_VERIFIED"
                  and report.get("native_history_restart") == "PASS"
                  and report.get("first_unmet_gate") ==
                  "NATIVE_ACTIVE_STOP_AND_FIVE_GUI_CLICKS_E07") else 2)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = {"schema": "nox.installed.qwen.e07-diagnostic.v1",
              "model": MODEL, "provider_stream": "NOT_RUN",
              "provider_abort": "NOT_RUN", "installed_native": "NOT_RUN",
              "native_active_stop": "NOT_TESTED",
              "native_history_restart": "NOT_TESTED",
              "independent_e07": "HOLD", "release_accepted": False}
    try:
        if not (sys.platform == "win32"
                and os.environ.get("GITHUB_ACTIONS") == "true"
                and os.environ.get("RUNNER_OS") == "Windows"
                and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
                and os.environ.get("GITHUB_REPOSITORY") ==
                    "MSSTXNEWS/nox-helion-pp-private-build"):
            raise RuntimeError("WINDOWS_HOST_NOT_AUTHORIZED")
        if not args.backend.is_file() or args.backend.is_symlink():
            raise RuntimeError("NOX_INSTALLED_BACKEND_MISSING")
        report["installed_backend_sha256"] = hashlib.file_digest(
            args.backend.open("rb"), "sha256").hexdigest()
        listing = get_json("/api/tags")
        candidates = [m for m in listing.get("models", [])
                      if isinstance(m, dict) and m.get("name") == MODEL]
        if len(candidates) != 1:
            raise RuntimeError("QWEN_MODEL_NOT_INSTALLED")
        digest = candidates[0].get("digest")
        if not (isinstance(digest, str)
                and re.fullmatch("[0-9a-f]{64}", digest)
                and digest.startswith(MODEL_DIGEST_PREFIX)):
            raise RuntimeError("QWEN_UPSTREAM_DIGEST_MISMATCH_HOLD")
        report["ollama_reported_digest"] = digest
        # Provider-reported tag/manifest metadata is never physical weights PASS.
        # Verify the complete approved manifest + every real local OCI blob
        # using the existing identity-locked SHA-256 verifier BEFORE inference.
        verified = verify_installed_model_oci_bytes(digest)
        report["independent_weight_sha_verified"] = True
        report["verified_model_manifest_sha256"] = verified["manifest_sha256"]
        report["verified_model_oci_blobs"] = verified["verified_blobs"]
        report["verified_model_oci_bytes"] = verified["verified_blob_bytes"]
        response = provider_stream(
            "Reply with a short Python function that returns 42.",
            limit=96)
        report["provider_stream"] = response
        if not response["done"] or response["nonempty_chunks"] < 1:
            raise RuntimeError("QWEN_REAL_GENERATION_NOT_PROVEN")
        aborted = provider_stream(
            "Write 1000 separate numbered lines describing computer memory.",
            limit=1024, early_cancel=True)
        report["provider_abort"] = aborted
        if not aborted["http_stream_closed_early"]:
            raise RuntimeError("QWEN_PROVIDER_STREAM_ABORT_NOT_OBSERVED")
        data_dir = Path(os.environ["RUNNER_TEMP"]) / "nox-qwen-native"
        model = native_request(args.backend, data_dir, "chat.model", {"model": MODEL}, 1)
        report["installed_native_model_ack"] = model["status"]
        if model["status"] != "OK":
            raise RuntimeError("NOX_INSTALLED_MODEL_SELECTION_HOLD")
        chat = native_request(
            args.backend, data_dir, "helion.chat",
            {"model": MODEL, "text": "Reply with exactly: NOX_QWEN_LIVE"}, 2)
        report["installed_native_chat_status"] = chat["status"]
        report["installed_native_chat_frames"] = chat["frame_count"]
        report["installed_native_generated_bytes"] = nonempty_response_text(chat)
        if chat["status"] != "OK" or report["installed_native_generated_bytes"] == 0:
            raise RuntimeError("NOX_INSTALLED_LIVE_CHAT_NOT_PROVEN")
        report["installed_native"] = "LIVE_NONEMPTY_RESPONSE_VERIFIED"
        # A distinct --native-stdio process MUST reload the answer from the
        # original installed SQLite store. A stream event or process-local
        # history is not proof of durable chat persistence.
        stored = native_request(args.backend, data_dir, "chat.history", {}, 3)
        report["native_history_restart_status"] = stored["status"]
        rows = []
        for item in stored["results"]:
            if isinstance(item, dict) and isinstance(item.get("messages"), list):
                rows = item["messages"]
        answers = {
            item["answer"] for item in chat["results"]
            if isinstance(item, dict) and isinstance(item.get("answer"), str)
            and item["answer"].strip()
        }
        if stored["status"] != "OK" or not answers or not rows:
            raise RuntimeError("NOX_INSTALLED_SQLITE_HISTORY_NOT_RELOADED_HOLD")
        exact_prompt = "Reply with exactly: NOX_QWEN_LIVE"
        matched_answer = None
        for i, item in enumerate(rows):
            if not (isinstance(item, dict) and item.get("role") == "user"
                    and item.get("content") == exact_prompt):
                continue
            for later in rows[i + 1:]:
                if (isinstance(later, dict) and later.get("role") == "assistant"
                        and later.get("content") in answers):
                    matched_answer = later["content"]
                    break
            if matched_answer is not None:
                break
        if matched_answer is None:
            raise RuntimeError("NOX_SQLITE_CHAT_RESPONSE_MISMATCH_AFTER_RESTART_HOLD")
        report["native_history_restart"] = "PASS"
        report["sqlite_history_rows_after_restart"] = len(rows)
        report["sqlite_reloaded_answer_sha256"] = hashlib.sha256(
            matched_answer.encode("utf-8")).hexdigest()
        # ACTIVE STOP is owned by the independent concurrent U04 physical gate.
        # NEVER conflate provider HTTP abort, idle STOP or SQLite with mid-stream STOP.
        report["first_unmet_gate"] = "NATIVE_ACTIVE_STOP_AND_FIVE_GUI_CLICKS_E07"
    except Exception as exc:
        report["first_unmet_gate"] = (
            str(exc)[:120] if isinstance(exc, RuntimeError)
            else "QWEN_PROBE_" + type(exc).__name__.upper() + "_HOLD")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print("NOX_QWEN_INSTALLED_FIRST_GATE", report["first_unmet_gate"], flush=True)
    return qwen_probe_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
