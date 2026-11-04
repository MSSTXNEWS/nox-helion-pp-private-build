"""Fail-closed physical active STOP diagnostic for the ORIGINAL installed NOX OneHost.

This is a verification client for the existing --native-stdio framed IPC, NOT
another backend or model implementation. A provider HTTP abort or idle STOP
never satisfies this gate. Full E07 and persisted history are separate gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import time
import uuid

PROTO = "NOX-P02-NATIVE-v1"
MAX_FRAME = 1_048_576


class GateHold(RuntimeError):
    pass


def _delta(frame: dict, nonce: str) -> bool:
    event = frame.get("event")
    return (frame.get("requestId") == nonce
            and frame.get("status") == "EVENT"
            and isinstance(event, dict)
            and event.get("route") == "helion.chat"
            and event.get("state") == "streaming"
            and isinstance(event.get("delta"), str)
            and bool(event["delta"].strip()))


def validate_stop_transcript(before: list[dict], after: list[dict],
                             chat_nonce: str, stop_nonce: str) -> dict:
    """Structural evidence ONLY; the live probe supplies observed pipe frames."""
    if not before or not any(_delta(f, chat_nonce) for f in before):
        raise GateHold("NOX_STOP_BEFORE_REAL_DELTA_HOLD")
    if any(f.get("requestId") == chat_nonce and f.get("status") != "EVENT"
           for f in before):
        raise GateHold("NOX_CHAT_FINISHED_BEFORE_STOP_HOLD")
    stops = [f for f in after if f.get("requestId") == stop_nonce
             and f.get("status") != "EVENT"]
    chats = [f for f in after if f.get("requestId") == chat_nonce
             and f.get("status") != "EVENT"]
    if len(stops) != 1 or stops[0].get("status") != "OK" or not isinstance(
            stops[0].get("result"), dict) or stops[0]["result"].get(
            "stopRequested") is not True:
        raise GateHold("NOX_NATIVE_ACTIVE_STOP_ACK_HOLD")
    if len(chats) != 1 or chats[0].get("status") != "HOLD" or chats[0].get(
            "errorCode") != "NATIVE_CHAT_STOP":
        raise GateHold("NOX_NATIVE_CHAT_NOT_INTERRUPTED_HOLD")
    return {"nonempty_deltas_before_stop": sum(_delta(f, chat_nonce) for f in before),
            "native_stop_ack": "PASS", "interrupted_chat_terminal": "NATIVE_CHAT_STOP"}


def _exact(reader, n: int) -> bytes:
    out = bytearray()
    while len(out) < n:
        block = reader.read(n - len(out))
        if not block:
            raise GateHold("NOX_PIPE_EOF_HOLD")
        out.extend(block)
    return bytes(out)


def _watch(reader, messages: queue.Queue) -> None:
    try:
        while True:
            first = reader.read(1)
            if first == b"":
                break
            size = struct.unpack(">I", first + _exact(reader, 3))[0]
            if not 0 < size <= MAX_FRAME:
                raise GateHold("NOX_NATIVE_FRAME_SIZE_HOLD")
            frame = json.loads(_exact(reader, size).decode("utf-8"))
            if not isinstance(frame, dict):
                raise GateHold("NOX_NATIVE_FRAME_TYPE_HOLD")
            messages.put(("frame", frame))
    except Exception as exc:
        messages.put(("error", type(exc).__name__))
    finally:
        messages.put(("eof", None))


def _send(pipe, run_id: str, nonce: str, route: str, payload: dict) -> None:
    data = json.dumps({"protocol": PROTO, "runId": run_id,
                       "requestId": nonce, "route": route, "payload": payload},
                      ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if not 0 < len(data) <= MAX_FRAME:
        raise GateHold("NOX_NATIVE_INPUT_SIZE_HOLD")
    pipe.write(struct.pack(">I", len(data)) + data)
    pipe.flush()


def live_active_stop(backend: Path, data_dir: Path, model: str) -> dict:
    run_id = "NOX-QWEN-STOP-" + uuid.uuid4().hex
    chat_nonce, stop_nonce = uuid.uuid4().hex, uuid.uuid4().hex
    proc = subprocess.Popen(
        [str(backend), "--native-stdio", "--run-id", run_id,
         "--data-dir", str(data_dir)], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
        cwd=str(backend.parent))
    messages: queue.Queue = queue.Queue()
    thread = threading.Thread(target=_watch, args=(proc.stdout, messages), daemon=True)
    thread.start()
    before, after = [], []
    try:
        _send(proc.stdin, run_id, chat_nonce, "helion.chat", {"model": model,
              "text": "Print 1200 separate numbered lines of Python code, one per line."})
        deadline = time.monotonic() + 120
        stopped = False
        while time.monotonic() < deadline:
            try:
                kind, item = messages.get(timeout=min(1, max(.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if kind != "frame":
                raise GateHold("NOX_NATIVE_PIPE_" + kind.upper() + "_HOLD")
            if (item.get("protocol") != PROTO or item.get("runId") != run_id
                    or item.get("requestId") not in (chat_nonce, stop_nonce)):
                raise GateHold("NOX_NATIVE_FRAME_IDENTITY_HOLD")
            if not stopped:
                before.append(item)
                if item.get("requestId") == chat_nonce and item.get("status") != "EVENT":
                    raise GateHold("NOX_CHAT_COMPLETED_BEFORE_ACTIVE_STOP_HOLD")
                if _delta(item, chat_nonce):
                    _send(proc.stdin, run_id, stop_nonce, "chat.stop", {})
                    stopped = True
                    deadline = min(deadline, time.monotonic() + 35)
            else:
                after.append(item)
                if (any(f.get("requestId") == stop_nonce and f.get("status") != "EVENT"
                        for f in after) and
                    any(f.get("requestId") == chat_nonce and f.get("status") != "EVENT"
                        for f in after)):
                    break
        if not stopped:
            raise GateHold("NOX_NATIVE_NONEMPTY_DELTA_TIMEOUT_HOLD")
        evidence = validate_stop_transcript(before, after, chat_nonce, stop_nonce)
        proc.stdin.close()
        if proc.wait(timeout=15) != 0:
            raise GateHold("NOX_NATIVE_PROCESS_EXIT_HOLD")
        return evidence
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        thread.join(timeout=3)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--backend", type=Path, required=True)
    p.add_argument("--data-dir", type=Path, required=True)
    p.add_argument("--model", default="qwen2.5-coder:1.5b")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    receipt = {"schema": "nox.native.active-stop.physical.v1",
               "native_active_stop": "HOLD", "history_restart": "NOT_TESTED",
               "independent_e07": "HOLD", "release_accepted": False}
    try:
        if not (sys.platform == "win32" and os.getenv("GITHUB_ACTIONS") == "true"
                and os.getenv("RUNNER_OS") == "Windows" and
                os.getenv("RUNNER_ENVIRONMENT") == "github-hosted" and
                os.getenv("GITHUB_REPOSITORY") == "MSSTXNEWS/nox-helion-pp-private-build"):
            raise GateHold("NOX_WINDOWS_PHYSICAL_RUNNER_REQUIRED")
        if not args.backend.is_file() or args.backend.is_symlink():
            raise GateHold("NOX_INSTALLED_BACKEND_MISSING")
        if not args.data_dir.is_dir() or args.data_dir.is_symlink() or args.data_dir.is_junction():
            raise GateHold("NOX_NATIVE_DATA_DIR_UNSAFE_HOLD")
        with args.backend.open("rb") as stream:
            receipt["backend_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        receipt.update(live_active_stop(args.backend, args.data_dir, args.model))
        receipt["native_active_stop"] = "PASS"
        receipt["first_unmet_gate"] = "HISTORY_RESTART_AND_INDEPENDENT_E07"
    except Exception as exc:
        receipt["first_unmet_gate"] = str(exc) if isinstance(exc, GateHold) else (
            "NOX_NATIVE_STOP_" + type(exc).__name__.upper() + "_HOLD")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print("NOX_NATIVE_ACTIVE_STOP_GATE", receipt["first_unmet_gate"], flush=True)
    return 0 if receipt["native_active_stop"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
