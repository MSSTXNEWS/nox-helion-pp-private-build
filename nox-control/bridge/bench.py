"""NOX 2A05: comparable read-only-of-S03 live chat latency samples.

Run explicitly on the owner host, *only after* current STOP/lease/resource admission:
  python bench.py --model-sha SHA256 --route-sha SHA1 --s03-revision REV --samples 20

Each request is ephemeral: reads normal S03 context but must never persist a turn.
This measures observed SSE chunks/s, NOT model tokens/s (chunks are not tokens).
"""
import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
import urllib.request
from urllib.error import HTTPError, URLError

URL = "http://127.0.0.1:8091/api/chat"
PROMPT = "Объясни в четырёх предложениях, как кэш промпта улучшает скорость ответа NOX."
# The WEB guard requires X-NOX-Token when this existing owner file is present.
# Credentials never belong in URLs, CLI arguments or measurement receipts.
OWNER_WEB_TOKEN_FILE = "/root/nox/state/web_token"
MAX_OWNER_WEB_TOKEN_BYTES = 4096


def _owner_web_token():
    """Read the private local WEB token once, before any benchmark POST.

    Missing token file permits the WEB guard's unauthenticated local path.
    Unreadable, symlinked, oversized or invalid token data must fail closed.
    """
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("HOLD_WEB_TOKEN_NOFOLLOW_UNAVAILABLE")
    try:
        fd = os.open(OWNER_WEB_TOKEN_FILE, flags | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError:
        raise ValueError("HOLD_WEB_TOKEN_UNVERIFIED") from None
    try:
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_OWNER_WEB_TOKEN_BYTES:
            raise ValueError("HOLD_WEB_TOKEN_UNVERIFIED")
        raw = os.read(fd, MAX_OWNER_WEB_TOKEN_BYTES + 1)
        if len(raw) > MAX_OWNER_WEB_TOKEN_BYTES:
            raise ValueError("HOLD_WEB_TOKEN_UNVERIFIED")
        token = raw.decode("ascii", "strict").strip()
        if token and any(not 33 <= ord(ch) <= 126 for ch in token):
            raise ValueError("HOLD_WEB_TOKEN_UNVERIFIED")
        return token or None
    except (OSError, UnicodeError):
        raise ValueError("HOLD_WEB_TOKEN_UNVERIFIED") from None
    finally:
        os.close(fd)



class UnsafeEphemeralWriteReceipt(ValueError):
    """An ephemeral benchmark may have written S03; never send another probe."""


# The HTTP peer controls the line length. urllib HTTPResponse.__iter__ uses
# unbounded readline(), which can exhaust the limited serving cgroup RAM
# before the existing post-read frame-size guard has a chance to run.
MAX_NDJSON_FRAME_BYTES = 1024 * 1024
# Bound cumulative wire data and event count, not just each individual line:
# a peer can otherwise send arbitrarily many valid 1 MiB frames over 400 s.
MAX_NDJSON_STREAM_BYTES = 8 * 1024 * 1024
MAX_NDJSON_STREAM_FRAMES = 4096


def _bounded_ndjson_lines(response):
    """Limit allocated bytes per wire line before decoding provider NDJSON.

    Real urllib HTTPResponse implements readline(size); keep __iter__ only for
    isolated legacy test doubles that do not expose a bounded reader.
    """
    reader = getattr(response, "readline", None)
    def wire_lines():
        if callable(reader):
            while True:
                raw = reader(MAX_NDJSON_FRAME_BYTES + 1)
                if not raw:
                    break
                yield raw
        else:
            # Legacy test doubles; production always takes the bounded reader.
            yield from response

    total_bytes = 0
    total_frames = 0
    for raw in wire_lines():
        if len(raw) > MAX_NDJSON_FRAME_BYTES:
            raise ValueError("OVERSIZED_FRAME")
        total_bytes += len(raw)
        total_frames += 1
        if total_bytes > MAX_NDJSON_STREAM_BYTES or total_frames > MAX_NDJSON_STREAM_FRAMES:
            raise ValueError("OVERSIZED_STREAM")
        yield raw



def _percentile(values, percentile):
    """Nearest-rank empirical quantile: no interpolation/fabricated observations."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


class _NoBenchmarkRedirect(urllib.request.HTTPRedirectHandler):
    """An owner-authenticated local POST must never follow redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_local_benchmark(request, timeout):
    # Do not inherit environment proxy configuration or forward the private
    # X-NOX-Token on a redirect. A redirect is an ambiguous POST outcome.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         _NoBenchmarkRedirect())
    return opener.open(request, timeout=timeout)


def _sample(index, clock=time.perf_counter, opener=_open_local_benchmark, auth_token=None):
    request_id = f"bench2a05-{index}-{time.monotonic_ns()}"
    data = {"request_id": request_id, "ephemeral": True, "use_memory": True,
            "messages": [{"role": "user", "content": PROMPT}],
            "options": {"num_predict": 200}, "mode": "auto"}
    headers = {"Content-Type": "application/json", "Accept": "application/x-ndjson"}
    if auth_token:
        headers["X-NOX-Token"] = auth_token
    req = urllib.request.Request(URL, data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                 headers=headers)
    started = clock()
    first = None
    chunks = []
    seq = 0
    stream_id = None
    terminal = None
    with opener(req, timeout=400) as response:
        if getattr(response, "status", 200) != 200:
            raise ValueError("HTTP_NOT_OK")
        # Production /api/chat emits exactly one complete NDJSON object per line.
        # A partial final line or invalid UTF-8 is never a successful sample.
        for raw in _bounded_ndjson_lines(response):
            if not raw.endswith(b"\n"):
                raise ValueError("TRUNCATED_FRAME")
            frame = json.loads(raw.decode("utf-8", "strict"))
            if not isinstance(frame, dict):
                raise ValueError("INVALID_FRAME")
            if frame.get("request_id") != request_id:
                raise ValueError("REQUEST_ID_MISMATCH")
            if not isinstance(frame.get("stream_id"), str):
                raise ValueError("MISSING_STREAM_ID")
            if stream_id is None:
                stream_id = frame["stream_id"]
            elif stream_id != frame["stream_id"]:
                raise ValueError("STREAM_ID_CHANGED")
            if type(frame.get("event_seq")) is not int or frame["event_seq"] != seq + 1:
                raise ValueError("CURSOR_GAP_OR_DUPLICATE")
            seq += 1
            if terminal is not None:
                raise ValueError("FRAME_AFTER_TERMINAL")
            if frame.get("status") == "HOLD":
                raise ValueError("STREAM_HOLD")
            message = frame.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if content:
                if not isinstance(content, str):
                    raise ValueError("NON_TEXT_CONTENT")
                if first is None:
                    first = clock()
                chunks.append(content)
            if frame.get("done") is True:
                terminal = frame
    ended = clock()
    if terminal is None or first is None or not chunks:
        raise ValueError("INCOMPLETE_STREAM")
    receipt = terminal.get("completion_receipt") or {}
    memory = terminal.get("memory_history") or {}
    write = terminal.get("memory_write_receipt") or {}
    if not all(isinstance(value, dict) for value in (receipt, memory, write)):
        raise UnsafeEphemeralWriteReceipt("BENCH_EPHEMERAL_WRITE_RISK")
    # A benchmark is observational, not training or chat history. If the
    # supposedly ephemeral request may have committed S03, stop the entire
    # sampling batch immediately instead of issuing another POST.
    if (memory.get("status") != "SKIPPED" or
            memory.get("reason") != "ephemeral" or
            write.get("status") != "SKIPPED" or
            write.get("s03_write_returned") is not False or
            write.get("s03_readback_verified") is not False):
        # Missing or ambiguous receipts are also unsafe to probe repeatedly.
        raise UnsafeEphemeralWriteReceipt("BENCH_EPHEMERAL_WRITE_RISK")
    if (terminal.get("done_reason") != "stop" or
            receipt.get("status") != "GENERATED" or receipt.get("upstream_done") is not True):
        raise ValueError("TERMINAL_RECEIPT_NOT_EPHEMERAL_GENERATED")
    full = "".join(chunks)
    if hashlib.sha256(full.encode("utf-8", "strict")).hexdigest() != terminal.get("digest"):
        raise ValueError("OUTPUT_DIGEST_MISMATCH")
    if terminal.get("frames") != len(chunks):
        raise ValueError("OUTPUT_CHUNK_COUNT_MISMATCH")
    model = terminal.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 256:
        raise ValueError("MODEL_ID_UNVERIFIED")
    total = ended - started
    ttft = first - started
    if not (total > ttft >= 0):
        raise ValueError("INVALID_TIMING")
    return {"ttft_s": round(ttft, 4), "total_s": round(total, 4),
            "chunks_per_s": round(len(chunks) / (ended - first), 4),
            "chunks": len(chunks), "output_utf8_bytes": len(full.encode("utf-8")),
            "token_per_s": None, "s03_write": "SKIPPED_EPHEMERAL",
            "model_reported": model}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-sha", required=True, help="Owner-verified installed model SHA-256 (not checked here)")
    ap.add_argument("--route-sha", required=True, help="Owner-verified installed bridge source git blob SHA-1")
    ap.add_argument("--s03-revision", required=True, help="Owner-verified S03 revision label")
    ap.add_argument("--samples", type=int, default=20)
    a = ap.parse_args(argv)
    if (not re.fullmatch(r"[0-9a-f]{64}", a.model_sha) or
            not re.fullmatch(r"[0-9a-f]{40}", a.route_sha) or
            not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", a.s03_revision) or
            not 20 <= a.samples <= 200):
        ap.error("owner pins must be valid; samples 20..200 for comparable p50/p95")
    # Preflight local WEB authentication BEFORE sending an ephemeral model POST.
    # Never publish the token, including on a failed or incomplete measurement.
    try:
        auth_token = _owner_web_token()
    except ValueError:
        print(json.dumps({"status": "HOLD_WEB_TOKEN_UNVERIFIED",
                          "original_task_id": "2A05", "planned": a.samples,
                          "completed": 0, "native_acceptance": False}, sort_keys=True))
        return 2
    observations = []
    errors = []
    unsafe_write = False
    # Any error after a POST may hide a completed S03 write. Even when the
    # response is truncated before a receipt, never send the next probe:
    # a different request_id is NOT a safe retry.
    ambiguous_outcome = False
    for index in range(a.samples):
        try:
            observations.append(_sample(index, auth_token=auth_token))
        except UnsafeEphemeralWriteReceipt:
            errors.append({"sample": index + 1, "error": "UnsafeEphemeralWriteReceipt",
                           "reason": "BENCH_EPHEMERAL_WRITE_RISK"})
            unsafe_write = True
            break
        except (HTTPError, URLError, OSError, ValueError, UnicodeError, TypeError) as exc:
            # A failed/truncated/invalid response cannot attest ephemeral
            # non-persistence. Continuing the batch would issue another POST.
            errors.append({"sample": index + 1, "error": type(exc).__name__,
                           "reason": str(exc)[:80] if isinstance(exc, ValueError) else "TRANSPORT_UNAVAILABLE"})
            ambiguous_outcome = True
            break
    models = {x["model_reported"] for x in observations}
    ok = len(observations) == a.samples and len(models) == 1
    result = {"status": ("HOLD_EPHEMERAL_WRITE_RISK" if unsafe_write else
                         "HOLD_PROBE_OUTCOME_UNKNOWN" if ambiguous_outcome else
                         "MEASURED_SOURCE_ONLY_PINS_UNVERIFIED" if ok else
                         "HOLD_INCOMPARABLE"),
              "original_task_id": "2A05", "model_sha_claim": a.model_sha,
              "route_sha_claim": a.route_sha, "s03_revision_claim": a.s03_revision,
              "model_reported": next(iter(models)) if len(models) == 1 else None,
              "endpoint": "/api/chat", "scenario_id": "NOX_2A05_CACHE_4_SENTENCES_V1",
              "ephemeral": True, "s03_reads": True,
              # An unobserved/unsafe POST may have committed. Report unknown,
              # never a negative write assertion based on missing evidence.
              "s03_writes": None if unsafe_write or ambiguous_outcome else False,
              "planned": a.samples, "completed": len(observations), "errors": errors,
              "tokens_per_second": None,
              "latency_s": ({name: {"p50": _percentile([v[name] for v in observations], .50),
                                     "p95": _percentile([v[name] for v in observations], .95)}
                             for name in ("ttft_s", "total_s")}) if ok else None,
              "observed_chunks_per_s": ({"p50": _percentile([v["chunks_per_s"] for v in observations], .50),
                                         "p95": _percentile([v["chunks_per_s"] for v in observations], .95)}) if ok else None,
              "native_acceptance": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
