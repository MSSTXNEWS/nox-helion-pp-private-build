"""Physical E07 preflight: interrupt real Qwen generation in the SAME installed
OneHost native-stdio process. This is NOT GUI, independent E07, or release proof.
Never confuse a provider HTTP close or idle STOP ACK with active NOX cancellation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading
import time

PROTOCOL = "NOX-P02-NATIVE-v1"
MODEL = "qwen2.5-coder:1.5b"


def exact_read(stream, size):
    result = bytearray()
    while len(result) < size:
        part = stream.read(size - len(result))
        if not part:
            raise EOFError("NATIVE_EOF_BEFORE_FRAME")
        result.extend(part)
    return bytes(result)


def test_active_stop(binary: Path, data_dir: Path) -> dict:
    if not binary.is_file() or binary.is_symlink():
        raise RuntimeError("INSTALLED_NATIVE_EXE_ABSENT")
    run_id = "NOX-E07-LIVE-STOP-SAME-PROCESS"
    responses: queue.Queue = queue.Queue()
    errors: queue.Queue = queue.Queue()
    process = subprocess.Popen(
        [str(binary), "--native-stdio", "--run-id", run_id,
         "--data-dir", str(data_dir)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=str(binary.parent), bufsize=0)
    writer_lock = threading.Lock()

    def send(route: str, payload: dict, nonce: str):
        envelope = {"protocol": PROTOCOL, "runId": run_id,
                    "requestId": nonce, "route": route, "payload": payload}
        raw = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        if len(raw) > 65536:
            raise RuntimeError("NATIVE_INPUT_TOO_LARGE")
        with writer_lock:
            process.stdin.write(struct.pack(">I", len(raw)) + raw)
            process.stdin.flush()

    def receive():
        try:
            while True:
                head = process.stdout.read(4)
                if not head:
                    break
                if len(head) != 4:
                    raise RuntimeError("NATIVE_FRAME_HEADER_TRUNCATED")
                n = struct.unpack(">I", head)[0]
                if not 0 < n <= 1048576:
                    raise RuntimeError("NATIVE_FRAME_SIZE_INVALID")
                frame = json.loads(exact_read(process.stdout, n).decode("utf-8"))
                if not isinstance(frame, dict):
                    raise RuntimeError("NATIVE_FRAME_NOT_OBJECT")
                if (frame.get("protocol") != PROTOCOL
                        or frame.get("runId") != run_id):
                    raise RuntimeError("NATIVE_FRAME_IDENTITY_INVALID")
                responses.put(frame)
        except Exception as exc:
            errors.put(type(exc).__name__)

    thread = threading.Thread(target=receive, daemon=True)
    thread.start()
    selection_id = "00000000000000000000000000001001"
    chat_id = "00000000000000000000000000001002"
    stop_id = "00000000000000000000000000001003"
    evidence = {"model_ack": False, "real_chat_delta_before_stop": False,
                "same_process_stop_ack": False, "terminal_after_stop": None,
                "chat_persisted_after_stop": "NOT_CHECKED",
                "live_stop_verified": False}
    try:
        def next_frame(deadline):
            while time.monotonic() < deadline:
                if not errors.empty():
                    raise RuntimeError("NATIVE_READER_" + errors.get() + "_HOLD")
                try:
                    return responses.get(timeout=min(0.5, max(.01, deadline-time.monotonic())))
                except queue.Empty:
                    if process.poll() is not None:
                        raise RuntimeError("NATIVE_PROCESS_EXIT_EARLY")
            raise RuntimeError("NATIVE_FRAME_TIMEOUT")

        send("chat.model", {"model": MODEL}, selection_id)
        deadline = time.monotonic() + 35
        while True:
            frame = next_frame(deadline)
            if frame.get("requestId") == selection_id and frame.get("status") != "EVENT":
                if frame.get("status") != "OK":
                    raise RuntimeError("NATIVE_MODEL_SELECTION_HOLD")
                evidence["model_ack"] = True
                break

        send("helion.chat", {"model": MODEL, "text":
             "Write 1500 individually numbered lines, each describing a different programming concept in one sentence."}, chat_id)
        deadline = time.monotonic() + 110
        while not evidence["real_chat_delta_before_stop"]:
            frame = next_frame(deadline)
            if frame.get("requestId") != chat_id:
                continue
            if frame.get("status") != "EVENT":
                raise RuntimeError("CHAT_FINISHED_BEFORE_ACTIVE_STOP")
            ev = frame.get("event")
            if (isinstance(ev, dict) and ev.get("route") == "helion.chat"
                    and isinstance(ev.get("delta"), str) and ev["delta"]):
                evidence["real_chat_delta_before_stop"] = True

        # STOP is sent to the SAME original process while its chat is active.
        send("chat.stop", {}, stop_id)
        deadline = time.monotonic() + 30
        while not evidence["same_process_stop_ack"] or evidence["terminal_after_stop"] is None:
            frame = next_frame(deadline)
            nonce = frame.get("requestId")
            status = frame.get("status")
            if nonce == stop_id and status != "EVENT":
                if status != "OK" or not isinstance(frame.get("result"), dict) or frame["result"].get("stopRequested") is not True:
                    raise RuntimeError("NATIVE_SAME_PROCESS_STOP_ACK_HOLD")
                evidence["same_process_stop_ack"] = True
            elif nonce == chat_id and status != "EVENT":
                evidence["terminal_after_stop"] = status
        if evidence["terminal_after_stop"] == "OK":
            raise RuntimeError("CHAT_COMPLETED_DESPITE_STOP")
        if evidence["terminal_after_stop"] != "HOLD":
            raise RuntimeError("CHAT_STOP_TERMINAL_NOT_HOLD")
        evidence["live_stop_verified"] = True
        return evidence
    finally:
        try:
            process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    receipt = {"schema":"nox.installed.active-stop.v1",
               "live_stop_verified": False, "e07_accepted": False}
    try:
        if not (sys.platform == "win32" and os.environ.get("GITHUB_ACTIONS") == "true"
                and os.environ.get("RUNNER_OS") == "Windows"
                and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
                and os.environ.get("GITHUB_REPOSITORY") == "MSSTXNEWS/nox-helion-pp-private-build"):
            raise RuntimeError("WINDOWS_RUNNER_NOT_AUTHORIZED")
        # Isolated data directory: the installed NOX is never modified.
        scratch = Path(os.environ["RUNNER_TEMP"]) / "nox-qwen-active-stop"
        if scratch.exists() or scratch.is_symlink():
            raise RuntimeError("STOP_DATA_PATH_COLLISION")
        receipt.update(test_active_stop(args.backend, scratch))
        receipt["first_unmet_gate"] = ("INDEPENDENT_E07_VISUAL_AND_HISTORY"
                                      if receipt["live_stop_verified"] else "NATIVE_STOP_HOLD")
    except Exception as exc:
        receipt["first_unmet_gate"] = (str(exc)[:110] if isinstance(exc, RuntimeError)
                                       else "STOP_" + type(exc).__name__ + "_HOLD")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("NOX_INSTALLED_ACTIVE_STOP", receipt["first_unmet_gate"])
    return 0 if receipt["live_stop_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
