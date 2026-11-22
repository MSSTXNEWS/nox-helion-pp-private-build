#!/usr/bin/env python3
"""probe.py: мелкие пробы здоровья для этапов S1_0N (только stdlib).
  probe.py health URL [--timeout 5]                      код 0 если HTTP 200
  probe.py chat --url http://127.0.0.1:8082 [--mode fast|deep|auto] [--max-tokens 24] [--timeout 60] [--system TXT] [--prompt TXT]
      стрим /v1/chat/completions, печатает одну JSON-строку {ok,ttft_s,total_s,chars,code,text}; код 0 если текст непустой
  probe.py completion --url http://127.0.0.1:8081 --system-file F [--prompt TXT] [--n 8]
      llama-server /completion с cache_prompt: {ok,ttft_s,prompt_n,cache_n}  (замер TTFT души)
"""
import argparse
import json
import sys
import time
import urllib.request


def _post(url, body, timeout):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def cmd_health(a):
    try:
        with urllib.request.urlopen(a.url, timeout=a.timeout) as r:
            return 0 if r.status == 200 else 1
    except Exception:
        return 1


def cmd_chat(a):
    body = {"messages": ([{"role": "system", "content": a.system}] if a.system else []) + [{"role": "user", "content": a.prompt}],
            "max_tokens": a.max_tokens, "stream": True, "temperature": 0.7}
    if a.mode:
        body["nox_mode"] = a.mode
    t0 = time.time()
    out = {"ok": False, "ttft_s": None, "total_s": None, "chars": 0, "code": None, "text": ""}
    try:
        with _post(a.url.rstrip("/") + "/v1/chat/completions", body, a.timeout) as r:
            out["code"] = r.status
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:") or line == "data: [DONE]":
                    continue
                try:
                    d = json.loads(line[5:])
                except ValueError:
                    continue
                ch = (d.get("choices") or [{}])[0]
                c = (ch.get("delta") or {}).get("content") or ch.get("text") or ""
                if c:
                    if out["ttft_s"] is None:
                        out["ttft_s"] = round(time.time() - t0, 3)
                    out["text"] += c
            out["chars"] = len(out["text"])
            out["ok"] = out["chars"] > 0
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, e)
    out["total_s"] = round(time.time() - t0, 3)
    out["text"] = out["text"][:120]
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_completion(a):
    soul = open(a.system_file, encoding="utf-8").read()
    body = {"prompt": soul + "\n\n" + a.prompt, "n_predict": a.n, "cache_prompt": True, "temperature": 0, "stream": True}
    t0 = time.time()
    out = {"ok": False, "ttft_s": None, "prompt_n": None, "cache_n": None}
    try:
        with _post(a.url.rstrip("/") + "/completion", body, a.timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    d = json.loads(line[5:])
                except ValueError:
                    continue
                if d.get("content") and out["ttft_s"] is None:
                    out["ttft_s"] = round(time.time() - t0, 3)
                if d.get("timings"):
                    out["prompt_n"] = d["timings"].get("prompt_n")
                    out["cache_n"] = d["timings"].get("cache_n")
            out["ok"] = out["ttft_s"] is not None
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, e)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    h = sp.add_parser("health"); h.add_argument("url"); h.add_argument("--timeout", type=float, default=5)
    c = sp.add_parser("chat"); c.add_argument("--url", default="http://127.0.0.1:8082"); c.add_argument("--mode", default="")
    c.add_argument("--max-tokens", type=int, default=24); c.add_argument("--timeout", type=float, default=60)
    c.add_argument("--system", default=""); c.add_argument("--prompt", default="Скажи одним словом: на связи?")
    k = sp.add_parser("completion"); k.add_argument("--url", default="http://127.0.0.1:8081"); k.add_argument("--system-file", required=True)
    k.add_argument("--prompt", default="Проверка связи."); k.add_argument("--n", type=int, default=8); k.add_argument("--timeout", type=float, default=1800)
    a = ap.parse_args(argv)
    return {"health": cmd_health, "chat": cmd_chat, "completion": cmd_completion}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
