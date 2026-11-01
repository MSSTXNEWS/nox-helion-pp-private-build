"""Exercise the built ORIGINAL Windows EXE over its existing framed stdio.

No model download, alternate backend, UI, database schema, or release verdict.
The private test data directory is isolated from user S03. A missing explicitly
approved installed model is HOLD, never a synthetic chat/stream/STOP PASS.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid

PROTOCOL = "NOX-P02-NATIVE-v1"
SCHEMA = "NOX_NATIVE_ONEHOST_SMOKE_V2"
ORIGINAL_SHA = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
SEED_SHA = "b1bc0c27997d76b4c654842101d28738080e8c83d3b077b12585aaa28b500c9f"
OPTIMIZER_SHA = "24c4f4c7ab5699863d945ba1299b2d903b6ed224ccb324b55e514682739b2c53"
SCOPE = {"core_id": "core.core", "persona_id": "persona.kairen_voss"}
ROUTES = ("chat.model", "chat.history", "chat.stop", "helion.chat")
MAX_FRAME = 1024 * 1024


class SmokeFailed(RuntimeError):
    pass


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plain_file(raw):
    path = Path(raw).absolute()
    for node in (path, *path.parents):
        info = node.lstat()
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise SmokeFailed("SMOKE_REPARSE_PATH_DENIED")
    if not path.is_file():
        raise SmokeFailed("SMOKE_REGULAR_FILE_REQUIRED")
    return path


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SmokeFailed("NATIVE_DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def reject_constant(_value):
    raise SmokeFailed("NATIVE_NONFINITE_JSON")


def finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise SmokeFailed("NATIVE_NONFINITE_JSON")
    return result


def decode_frame(raw, run_id, pending):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_FRAME:
        raise SmokeFailed("NATIVE_FRAME_LENGTH_INVALID")
    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                            parse_constant=reject_constant, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise SmokeFailed("NATIVE_FRAME_JSON_INVALID") from exc
    if (type(result) is not dict or result.get("protocol") != PROTOCOL or
            result.get("runId") != run_id or result.get("requestId") not in pending):
        raise SmokeFailed("NATIVE_RUN_OR_REQUEST_ID_MISMATCH")
    if result.get("status") == "EVENT":
        if set(result) != {"protocol","runId","requestId","status","event"} or type(result.get("event")) is not dict:
            raise SmokeFailed("NATIVE_EVENT_SHAPE_INVALID")
    elif result.get("status") == "OK":
        if set(result) != {"protocol","runId","requestId","status","result"}:
            raise SmokeFailed("NATIVE_RESULT_MISSING")
    elif result.get("status") == "HOLD":
        if (set(result) != {"protocol","runId","requestId","status","errorCode"} or
                not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", str(result.get("errorCode", "")))):
            raise SmokeFailed("NATIVE_HOLD_CODE_INVALID")
    else:
        raise SmokeFailed("NATIVE_STATUS_INVALID")
    return result


def safe_native_stderr_hint(path):
    """Only stable exception class/module names; never log arbitrary stderr or PII."""
    try:
        tail = Path(path).read_bytes()[-65536:].decode("utf-8", errors="replace")
    except (OSError, UnicodeError):
        return "STDERR_UNAVAILABLE"
    patterns = (
        ("PY_MODULE_MISSING", r"""ModuleNotFoundError:\s+No module named ['"]([A-Za-z_][A-Za-z_0-9.]{0,99})['"]"""),
        ("PY_IMPORT_MISSING", r"""ImportError:\s+cannot import name ['"]([A-Za-z_][A-Za-z_0-9]{0,99})['"]"""),
    )
    for kind, regex in patterns:
        found = re.search(regex, tail)
        if found:
            return kind + ":" + found.group(1)
    if "Failed to load Python DLL" in tail:
        return "PYTHON_DLL_LOAD_FAILED"
    if "Traceback (most recent call last)" in tail:
        # The exception class and last Python basename/line are bounded metadata.
        # Do not expose exception messages, raw stderr, or host file paths.
        classes = re.findall(
            r"(?m)^(?:[A-Za-z_][A-Za-z_0-9.]*[.])?([A-Za-z_][A-Za-z_0-9]*(?:Error|Exception)|SystemExit|KeyboardInterrupt):",
            tail)
        locations = re.findall(
            r'File "([^"\\r\\n]{1,500}\\.py)", line ([1-9][0-9]{0,6})', tail)
        detail = "PYTHON_TRACEBACK"
        if classes:
            detail += ":" + classes[-1]
        if locations:
            filename, lineno = locations[-1]
            filename = filename.replace("\\\\", "/").split("/")[-1]
            if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.-]{0,99}\\.py", filename):
                detail += ":" + filename + ":" + lineno
        return detail
    if "FATAL" in tail.upper():
        return "NATIVE_FATAL_DIAGNOSTIC_PRESENT"
    return "STDERR_PRESENT_UNCLASSIFIED" if tail else "STDERR_EMPTY"


class NativeExe:
    """Exactly one actual executable child; STOP can overtake its chat request."""
    def __init__(self, exe, data_dir, run_id, stderr_file):
        self.run_id = run_id
        self.pending = set()
        self.frames = []
        self._received = queue.Queue(maxsize=4096)
        self._stderr = Path(stderr_file).open("wb")
        self.process = subprocess.Popen([str(exe), "--native-stdio", "--run-id", run_id,
            "--data-dir", str(data_dir)], cwd=str(Path(exe).parent), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=self._stderr, bufsize=0,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.reader = threading.Thread(target=self._read, name="NOX-native-smoke-reader", daemon=True)
        self.reader.start()

    def _read_exact(self, count):
        data = bytearray()
        while len(data) < count:
            block = self.process.stdout.read(count - len(data))
            if not block:
                raise SmokeFailed("NATIVE_EXECUTABLE_CLOSED_PIPE")
            data.extend(block)
        return bytes(data)

    def _read(self):
        try:
            while True:
                size = struct.unpack(">I", self._read_exact(4))[0]
                if not 0 < size <= MAX_FRAME:
                    raise SmokeFailed("NATIVE_BINARY_FRAME_LENGTH_INVALID")
                self._received.put(self._read_exact(size), timeout=2)
        except Exception as exc:
            try:
                self._received.put(exc, timeout=2)
            except queue.Full:
                pass

    def send(self, route, payload):
        nonce = uuid.uuid4().hex
        body = json.dumps({"protocol": PROTOCOL, "runId": self.run_id,
            "requestId": nonce, "route": route, "payload": payload},
            ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.pending.add(nonce)
        try:
            packet = memoryview(struct.pack(">I", len(body)) + body)
            while packet:
                count = self.process.stdin.write(packet)
                if type(count) is not int or not 0 < count <= len(packet):
                    raise SmokeFailed("NATIVE_EXECUTABLE_WRITE_STALLED")
                packet = packet[count:]
            self.process.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise SmokeFailed("NATIVE_EXECUTABLE_WRITE_FAILED") from exc
        return nonce

    def receive(self, deadline):
        try:
            raw = self._received.get(timeout=max(0.01, deadline - time.monotonic()))
        except queue.Empty as exc:
            raise SmokeFailed("NATIVE_EXE_REPLY_TIMEOUT") from exc
        if isinstance(raw, Exception):
            raise SmokeFailed("NATIVE_EXECUTABLE_PIPE_FAILED") from raw
        frame = decode_frame(raw, self.run_id, self.pending)
        self.frames.append({"request_id": frame["requestId"], "status": frame["status"],
                            "frame_sha256": hashlib.sha256(raw).hexdigest()})
        if frame["status"] != "EVENT":
            self.pending.remove(frame["requestId"])
        return frame

    def request(self, route, payload, timeout):
        nonce = self.send(route, payload)
        deadline = time.monotonic() + timeout
        events = []
        while True:
            frame = self.receive(deadline)
            if frame["requestId"] != nonce:
                raise SmokeFailed("NATIVE_UNEXPECTED_CONCURRENT_REPLY")
            if frame["status"] == "EVENT":
                events.append(frame["event"])
            else:
                return frame, events

    def close(self):
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=10)
        self._stderr.close()
        return self.process.returncode


def accepted(frame):
    if frame.get("status") != "OK" or type(frame.get("result")) is not dict:
        raise SmokeFailed("NATIVE_REQUIRED_ROUTE_REJECTED_" + str(frame.get("errorCode", "UNKNOWN")))
    return frame["result"]


def history(client, timeout, scope=None):
    frame, events = client.request("chat.history", dict(SCOPE if scope is None else scope), timeout)
    rows = accepted(frame).get("messages")
    if (events or type(rows) is not list or any(type(row) is not dict or
            row.get("role") not in {"user", "assistant"} or type(row.get("content")) is not str for row in rows)):
        raise SmokeFailed("NATIVE_ORIGINAL_HISTORY_SHAPE_INVALID")
    return rows


def assert_lineage(value):
    lineage = value.get("lineage")
    if (type(lineage) is not dict or lineage.get("S03") != "ORIGINAL_STORE_READY" or
            lineage.get("seed_archive_sha256") != SEED_SHA or lineage.get("optimizer_sha256") != OPTIMIZER_SHA or
            lineage.get("SEED") != "ORIGINAL_BYTES_VERIFIED_NOT_RELEASE_ACCEPTED"):
        raise SmokeFailed("NATIVE_SEED_OR_ORIGINAL_S03_LINEAGE_FAILED")
    return {key: lineage[key] for key in ("S03", "SEED", "seed_archive_sha256", "optimizer_sha256")}


def exercise_routes(client, model, timeout):
    proof = {route: {"status": "NOT_RUN"} for route in ROUTES}
    inventory, _ = client.request("chat.model", {}, timeout)
    inventory = accepted(inventory)
    models = inventory.get("models")
    if type(models) is not list or any(type(tag) is not str for tag in models):
        raise SmokeFailed("NATIVE_MODEL_INVENTORY_INVALID")
    lineage = assert_lineage(inventory)
    proof["chat.model"] = {"status": "PASS", "installed_count": len(models),
        "provider_state": inventory.get("provider_state"), "selection": "NOT_RUN"}
    if history(client, timeout) != []:
        raise SmokeFailed("ISOLATED_TEST_HISTORY_WAS_NOT_EMPTY")
    proof["chat.history"] = {"status": "PASS", "offline_read": True, "restart": "NOT_RUN"}
    stop, _ = client.request("chat.stop", {}, timeout)
    if accepted(stop).get("stopRequested") is not True or history(client, timeout) != []:
        raise SmokeFailed("NATIVE_IDLE_STOP_NOT_ACKNOWLEDGED_OR_MUTATED_HISTORY")
    proof["chat.stop"] = {"status": "PASS", "idle_ack": True, "live_cancel": "NOT_RUN"}
    if not model or model not in models:
        proof["helion.chat"] = {"status": "HOLD", "reason":
            "EXPLICIT_APPROVED_INSTALLED_MODEL_REQUIRED" if not model else "APPROVED_MODEL_NOT_INSTALLED"}
        proof["chat.stop"]["live_cancel"] = "HOLD_NO_APPROVED_MODEL"
        return proof, lineage, []
    selected, _ = client.request("chat.model", {"model": model, **SCOPE}, timeout)
    selected = accepted(selected)
    if selected.get("selectedModel") != model or assert_lineage(selected) != lineage:
        raise SmokeFailed("NATIVE_MODEL_SELECTION_OR_SEED_PRESERVATION_FAILED")
    proof["chat.model"]["selection"] = "PASS"
    prompt = "Reply with one short greeting for this isolated NOX acceptance check " + uuid.uuid4().hex
    response, events = client.request("helion.chat", {**SCOPE, "text": prompt}, timeout)
    response = accepted(response)
    if (response.get("done") is not True or type(response.get("answer")) is not str or not response["answer"] or
            not any(type(item.get("delta")) is str and item["delta"] for item in events)):
        raise SmokeFailed("NATIVE_REAL_CHAT_OR_STREAM_EVENT_MISSING")
    completed = history(client, timeout)
    if len(completed) != 2 or completed[0]["content"] != prompt or completed[1]["content"] != response["answer"]:
        raise SmokeFailed("NATIVE_CHAT_EXCHANGE_NOT_PERSISTED")
    other = {**SCOPE, "persona_id": "persona.adrian_marrow"}
    if history(client, timeout, other):
        raise SmokeFailed("NATIVE_PERSONA_HISTORY_ISOLATION_FAILED")
    proof["helion.chat"] = {"status": "PASS", "real_stream_event_count": len(events),
        "answer_sha256": hashlib.sha256(response["answer"].encode()).hexdigest(),
        "persistent_exchange": True, "persona_isolation": True}
    # STOP is tested after an actual model delta, never before model execution.
    nonce = client.send("helion.chat", {**SCOPE, "text":
        "For this isolated cancellation test, write a long numbered list of 500 astronomy facts. "
        "Start with item 1 and continue until all 500 items are complete."})
    deadline = time.monotonic() + timeout
    stop_nonce = None
    chat_terminal = stop_terminal = None
    while chat_terminal is None or stop_nonce is not None and stop_terminal is None:
        frame = client.receive(deadline)
        if frame["requestId"] == nonce:
            if frame["status"] == "EVENT":
                if stop_nonce is None and frame["event"].get("delta"):
                    stop_nonce = client.send("chat.stop", {})
            else:
                chat_terminal = frame
        elif frame["requestId"] == stop_nonce:
            if frame["status"] == "EVENT":
                raise SmokeFailed("NATIVE_STOP_EMITTED_MODEL_EVENT")
            stop_terminal = frame
        else:
            raise SmokeFailed("NATIVE_LIVE_STOP_WRONG_REQUEST")
    if stop_nonce is None:
        proof["chat.stop"]["live_cancel"] = "HOLD_NO_CANCELLABLE_STREAM"
    elif accepted(stop_terminal).get("stopRequested") is not True:
        raise SmokeFailed("NATIVE_LIVE_STOP_NOT_ACKNOWLEDGED")
    elif chat_terminal.get("status") == "HOLD" and chat_terminal.get("errorCode") == "NATIVE_CHAT_STOP":
        if history(client, timeout) != completed:
            raise SmokeFailed("NATIVE_CANCELLED_EXCHANGE_WAS_PERSISTED")
        proof["chat.stop"]["live_cancel"] = "PASS"
        proof["chat.stop"]["terminal_code"] = "NATIVE_CHAT_STOP"
    elif chat_terminal.get("status") == "OK":
        proof["chat.stop"]["live_cancel"] = "HOLD_MODEL_COMPLETED_BEFORE_STOP"
    else:
        raise SmokeFailed("NATIVE_STOP_WAS_CONFUSED_WITH_TIMEOUT_OR_PROVIDER_FAILURE")
    return proof, lineage, history(client, timeout)


def verify_build(exe, receipt_path, source_head):
    receipt_path = plain_file(receipt_path)
    build = json.loads(receipt_path.read_text("utf-8"), object_pairs_hook=unique_object)
    if (build.get("schema") != "NOX-ONEHOST-PYTHON-BUILD-V1" or
            build.get("source_commit") != source_head or build.get("release_accepted") is not False or
            build.get("bundled_runtime_data_verified") is not True or
            build.get("python_exe_sha256") != sha256(exe)):
        raise SmokeFailed("EXACT_ONEHOST_BUILD_RECEIPT_REQUIRED")
    if Path(build.get("python_exe", "")).resolve() != exe.resolve():
        raise SmokeFailed("BUILT_EXECUTABLE_PATH_MISMATCH")
    archive = plain_file(build["original_archive_path"])
    app = plain_file(build["staged_original_app_path"])
    if (sha256(archive) != ORIGINAL_SHA or build.get("source_original_archive_sha256") != ORIGINAL_SHA or
            sha256(app) != build.get("staged_original_app_sha256")):
        raise SmokeFailed("ORIGINAL_OR_STAGED_SOURCE_PROVENANCE_FAILED")
    return build, archive, app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--build-receipt", required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    proof = {"schema": SCHEMA, "phase": "NATIVE_STDIO_SMOKE_NOT_RUN", "source_commit": args.source_head,
        "started_utc":datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform, "transport_status": "NOT_RUN", "offline_backbone_status": "NOT_RUN",
        "live_model_status": "NOT_RUN", "native_windows_exe_request_reply": "NOT_RUN",
        "installed_wpf_e07": False, "release_accepted": False, "routes": {},
        "run_id_matched": False, "request_id_matched": False, "original_729_unchanged": False}
    exit_code = 1
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.source_head) or not 10 <= args.timeout <= 600:
            raise SmokeFailed("SMOKE_SOURCE_HEAD_OR_TIMEOUT_INVALID")
        exe = plain_file(args.exe)
        with exe.open("rb") as stream:
            pe_magic = stream.read(2)
        if exe.suffix.lower() != ".exe" or pe_magic != b"MZ":
            raise SmokeFailed("ACTUAL_WINDOWS_PE_EXECUTABLE_REQUIRED")
        build, archive, app = verify_build(exe, args.build_receipt, args.source_head)
        proof.update(exe_file=exe.name, exe_sha256=sha256(exe),
            source_original_archive_sha256=ORIGINAL_SHA,
            staged_original_app_sha256=sha256(app), build_receipt_sha256=sha256(args.build_receipt),
            build_run_id=build.get("run_id"),source_tree=build.get("source_tree"))
        if sys.platform != "win32":
            proof.update(phase="BUILT_AND_NATIVE_STDIO_SMOKE_HOLD", native_windows_exe_request_reply="HOLD",
                         reason="ACTUAL_WINDOWS_HOST_REQUIRED")
            exit_code = 2
        else:
            with tempfile.TemporaryDirectory(prefix="NOX-native-acceptance-") as temp:
                root = Path(temp);data = root / "S03";data.mkdir()
                run_id = "NOX-NATIVE-SMOKE-" + uuid.uuid4().hex
                client = NativeExe(exe, data, run_id, root / "stderr-first.log")
                try:
                    routes, lineage, stored = exercise_routes(client, args.model, args.timeout)
                finally:
                    returncode = client.close()
                    proof["frames"]=list(client.frames)
                    proof["first_stderr_sha256"]=sha256(root / "stderr-first.log")
                    proof["first_stderr_hint"]=safe_native_stderr_hint(root / "stderr-first.log")
                if returncode != 0:
                    raise SmokeFailed("NATIVE_EXECUTABLE_SHUTDOWN_FAILED")
                first_frames = client.frames
                second = NativeExe(exe, data, run_id + "-RESTART", root / "stderr-restart.log")
                try:
                    if history(second, args.timeout) != stored:
                        raise SmokeFailed("NATIVE_HISTORY_LOST_AFTER_PROCESS_RESTART")
                    inventory, _ = second.request("chat.model", {}, args.timeout)
                    if assert_lineage(accepted(inventory)) != lineage:
                        raise SmokeFailed("NATIVE_SEED_CHANGED_AFTER_RESTART")
                finally:
                    returncode = second.close()
                    proof["frames"].extend(second.frames)
                    proof["restart_stderr_sha256"]=sha256(root / "stderr-restart.log")
                if returncode != 0:
                    raise SmokeFailed("NATIVE_RESTART_SHUTDOWN_FAILED")
                routes["chat.history"]["restart"] = "PASS" if stored else "EMPTY_STATE_ONLY"
                if sha256(exe) != proof["exe_sha256"] or sha256(archive) != ORIGINAL_SHA or sha256(app) != proof["staged_original_app_sha256"]:
                    raise SmokeFailed("SMOKE_SOURCE_OR_EXECUTABLE_CHANGED_DURING_TEST")
                complete = routes["helion.chat"]["status"] == "PASS" and routes["chat.stop"]["live_cancel"] == "PASS"
                proof.update(phase="BUILT_AND_NATIVE_STDIO_SMOKE_PASS" if complete else "BUILT_AND_NATIVE_STDIO_SMOKE_HOLD",
                    transport_status="PASS", offline_backbone_status="PASS", live_model_status="PASS" if complete else "HOLD",
                    native_windows_exe_request_reply="PASS" if complete else "HOLD", routes=routes, lineage=lineage,
                    supported_routes_verified=[route for route in ROUTES if routes[route]["status"] == "PASS"],
                    supported_route_verified="chat.model", run_id=run_id, run_id_matched=True,
                    request_id_matched=True, original_729_unchanged=True,
                    process_restart_verified=True, isolated_test_data=True,
                    history_persistence_verified=bool(stored),
                    frames=first_frames+second.frames, concurrent_native_executables_max=1)
                exit_code = 0 if complete else 2
    except Exception as exc:
        code = str(exc)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,149}", code):
            code = type(exc).__name__.upper()
        proof.update(phase="BUILT_AND_NATIVE_STDIO_SMOKE_FAILED", native_windows_exe_request_reply="FAILED", reason=code)
    proof["completed_utc"]=datetime.now(timezone.utc).isoformat()
    output = Path(args.output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(proof, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"schema": SCHEMA, "phase": proof["phase"],
        "native_windows_exe_request_reply": proof["native_windows_exe_request_reply"],
        "receipt_sha256": sha256(output),
        "first_stderr_hint": proof.get("first_stderr_hint", "NOT_APPLICABLE")}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
