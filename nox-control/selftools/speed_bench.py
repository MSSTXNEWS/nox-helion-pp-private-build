"""speed_bench: stream /v1/chat/completions, measure TTFT and tokens/s."""
import json
import time
import urllib.error
import urllib.request
import registry as R


def bench_once(url, model, prompt, max_tokens, timeout):
    body = json.dumps({"model": model, "stream": True, "max_tokens": max_tokens, "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    first, n = None, 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            try:
                d = json.loads(line[5:])
                delta = d["choices"][0].get("delta", {})
            except (ValueError, KeyError, IndexError):
                continue
            if delta.get("content") or delta.get("reasoning_content"):
                if first is None:
                    first = time.time()
                n += 1  # one SSE chunk ~ one token in llama.cpp
    t1 = time.time()
    if first is None:
        raise ValueError("no tokens streamed")
    gen = max(t1 - first, 1e-6)
    return {"ttft_s": round(first - t0, 4), "tokens": n, "tok_s": round((n - 1) / gen, 2) if n > 1 else 0.0,
            "total_s": round(t1 - t0, 3)}


@R.register("speed_bench", "read", {"properties": {
    "endpoint": {"type": "string", "default": "http://127.0.0.1:8098"}, "model": {"type": "string", "default": "default"},
    "prompt": {"type": "string", "default": "Count from 1 to 40 in words."}, "max_tokens": {"type": "integer", "default": 128},
    "runs": {"type": "integer", "default": 3}, "timeout": {"type": "integer", "default": 120}}},
    "TTFT and tok/s over N streamed runs against /v1/chat/completions.")
def speed_bench(a):
    url = a["endpoint"].rstrip("/") + "/v1/chat/completions"
    runs = []
    for _ in range(max(1, min(a["runs"], 20))):
        try:
            runs.append(bench_once(url, a["model"], a["prompt"], a["max_tokens"], a["timeout"]))
        except (urllib.error.URLError, OSError) as e:
            return R.blocked("endpoint unreachable: %s" % getattr(e, "reason", e), "start the model server at " + a["endpoint"])
        except ValueError as e:
            return R.fail(e)
    avg = lambda k: round(sum(r[k] for r in runs) / len(runs), 3)
    return {"ok": True, "runs": runs, "avg_ttft_s": avg("ttft_s"), "avg_tok_s": avg("tok_s")}
