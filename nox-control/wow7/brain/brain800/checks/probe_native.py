"""End-to-end Brain800 probe against a local, patched, unpacked NOX CORE.

Usage: python probe_native.py /path/to/patched/nox_wow/BRAIN
The server and the client use localhost. The state lives in a temporary
directory retained across two fresh server processes and then removed.
"""
from contextlib import contextmanager
import argparse
import http.client
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time


def require(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def serve(brain, state):
    port = free_port()
    env = os.environ.copy()
    # Keep defaults for the brain adapter. Do not let local settings send a
    # probe to the live model or change its database or force eval mode.
    for key in list(env):
        if key.startswith("NOX_"):
            del env[key]
    env.update(NOX_STATE=str(state / "state"), NOX_RECEIPTS=str(state / "receipts"),
               NOX_TRACE_DIR=str(state / "traces"), NOX_CORE_HOST="127.0.0.1",
               NOX_CORE_PORT=str(port), NOX_FAST_URL="http://127.0.0.1:1",
               NOX_GLM_URL="http://127.0.0.1:1", NOX_BG_DEEP="0",
               PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryFile(mode="w+b") as log:
        proc = subprocess.Popen([sys.executable, str(brain / "nox_core.py")],
                                cwd=brain, env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline and proc.poll() is None:
                con = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                try:
                    con.request("GET", "/health")
                    response = con.getresponse()
                    if response.status == 200:
                        response.read()
                        break
                except OSError:
                    pass
                finally:
                    con.close()
                time.sleep(.08)
            else:
                raise RuntimeError("CORE did not become ready on its temporary port")
            yield port
        except BaseException:
            log.seek(0)
            sys.stderr.write(log.read().decode("utf-8", "replace")[-6000:])
            raise
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def chat(port, scope, turn, text, stream=False):
    payload = {"model": "nox", "messages": [{"role": "user", "content": text}], "stream": stream}
    con = http.client.HTTPConnection("127.0.0.1", port, timeout=25)
    try:
        con.request("POST", "/v1/chat/completions", json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    {"Content-Type": "application/json", "X-NOX-Conversation": scope, "X-NOX-Turn-ID": turn})
        response = con.getresponse()
        body = response.read().decode("utf-8")
        require(response.status == 200, f"HTTP {response.status}: {body[:500]}")
        mime = response.getheader("Content-Type", "")
    finally:
        con.close()
    if not stream:
        require("application/json" in mime, f"Expected ordinary JSON, got {mime}")
        item = json.loads(body)
        require(item["id"] == turn, "Mismatched ordinary completion ID")
        return item["choices"][0]["message"]["content"].strip()
    require("text/event-stream" in mime, f"Expected SSE, got {mime}")
    items = []
    finished = False
    for frame in body.replace("\r\n", "\n").split("\n\n"):
        fields = frame.splitlines()
        if any(line.startswith("event:") for line in fields):
            continue
        data = "\n".join(line[5:].lstrip(" ") for line in fields if line.startswith("data:"))
        if data == "[DONE]":
            finished = True
        elif data:
            require(not finished, "SSE contained data after [DONE]")
            chunk = json.loads(data)
            require(chunk["id"] == turn, "Mismatched SSE completion ID")
            items.append(chunk["choices"][0]["delta"].get("content", ""))
    require(finished, "SSE stream ended without [DONE]")
    return "".join(items).strip()


def run(brain):
    require((brain / "nox_core.py").is_file(), f"Missing {brain}/nox_core.py")
    phrase = "Свет в конце"
    create = "Запомни замысел: " + phrase
    show = "Покажи замыслы"
    scope = "probe-scope-alpha"
    turn = "probe-save-one"
    with tempfile.TemporaryDirectory(prefix="nox-native800-") as tmp:
        root = Path(tmp)
        for name in ("state", "receipts", "traces"):
            (root / name).mkdir()
        with serve(brain, root) as port:
            first = chat(port, scope, turn, create)
            require(first == "Сохранил: " + phrase, f"Unexpected save reply: {first!r}")
            again = chat(port, scope, turn, create)
            require(again == first, "Replay returned different result")
            normal = chat(port, scope, "probe-show-json", show)
            streamed = chat(port, scope, "probe-show-sse", show, True)
            require(normal == streamed and normal == "• " + phrase, f"Recall mismatch: {normal!r}, {streamed!r}")
            other = chat(port, "probe-scope-beta", "probe-other", show, True)
            require(other == "В этой беседе таких записей пока нет.", f"Expected isolated empty scope: {other!r}")
            raw = chat(port, scope, "probe-timeline", '/brain studio.pause.duration {"scene":{"pause":[{"id":"a","start":0,"end":300}]}}')
            require(json.loads(raw) == {"occupied_ms": 300, "span_ms": 300}, f"Wrong studio duration: {raw!r}")
        with serve(brain, root) as port:
            require(chat(port, scope, "probe-after-restart", show, True) == normal,
                    "SSE failed to recall record after restart")
            require(chat(port, scope, turn, create) == first, "Replay after restart differs")
            require(chat(port, scope, "probe-count", show) == normal, "Retry duplicated visible entry")
        # Read-only evidence below catches invisible duplicate versions as well.
        db = root / "state" / "brain800.sqlite3"
        require(db.is_file(), "No journal in temporary NOX_STATE")
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as connection:
            stored = connection.execute("SELECT COUNT(*) FROM entries WHERE scope=? AND text=?", (scope, phrase)).fetchone()[0]
            receipts = connection.execute("SELECT COUNT(*) FROM receipts WHERE scope=? AND token=?", (scope, turn)).fetchone()[0]
            require((stored, receipts) == (1, 1), f"Replay produced {stored} versions, {receipts} receipts")
    return {"result": "PASS", "route": "/v1/chat/completions", "server_processes": 2,
            "content": normal, "sse_matches_json": True, "scope_isolated": True,
            "restart_recall": True, "duplicate_write_versions": stored - 1,
            "duration_ms": 300, "model_called_by_probe": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brain", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.brain.resolve()), ensure_ascii=False, indent=2))
