#!/usr/bin/env python3
"""NOX advisors: consult local OpenAI-compatible llama.cpp servers. Stdlib only.

Advisor output is DATA: never executed, capped at MAX_ANSWER chars.
Network: only URLs from the config and the embed URL.
"""
import argparse
import json
import math
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

MAX_ANSWER = 8000
DEFAULT_EMBED_URL = "http://127.0.0.1:8082/v1/embeddings"
REVIEW_ROLES = ("judge", "checker")

REVIEW_SYSTEM = (
    "You are a strict reviewer. Reply ONLY with JSON: "
    '{"verdict":"pass"|"fail","reasons":["..."]}. '
    "Pass only if the candidate answer fully satisfies the acceptance criteria."
)


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, list):
        raise ValueError("config must be a JSON list")
    return cfg


def _post_json(url, payload, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _chat_url(base):
    base = base.rstrip("/")
    return base if base.endswith("/chat/completions") else base + "/v1/chat/completions"


def _ask_one(adv, question, system):
    t0 = time.monotonic()
    res = {"name": adv.get("name", "?"), "ok": False, "answer": "",
           "latency_s": 0.0, "error": None, "role": adv.get("role")}
    try:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": question})
        data = _post_json(_chat_url(adv["url"]),
                          {"messages": msgs, "temperature": 0.2},
                          float(adv.get("timeout_s", 60)))
        text = data["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError("non-string content")
        res["answer"] = text[:MAX_ANSWER]
        res["ok"] = True
    except Exception as e:  # dead/slow advisor must not break the call
        res["error"] = f"{type(e).__name__}: {e}"[:500]
    res["latency_s"] = round(time.monotonic() - t0, 3)
    return res


def ask_advisors(question, config_path, system=None, _advisors=None):
    advs = _advisors if _advisors is not None else load_config(config_path)
    if not advs:
        return []
    with ThreadPoolExecutor(max_workers=len(advs)) as ex:
        return list(ex.map(lambda a: _ask_one(a, question, system), advs))


# ---------- consensus ----------
def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _tokens(s):
    return set(re.findall(r"\w+", s.lower()))


def _jaccard(a, b):
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / len(ta | tb)


def _embed(texts, embed_url):
    data = _post_json(embed_url, {"input": texts, "model": "bge-m3"}, 20)
    items = sorted(data["data"], key=lambda d: d.get("index", 0))
    vecs = [d["embedding"] for d in items]
    if len(vecs) != len(texts):
        raise ValueError("embedding count mismatch")
    return vecs


def consensus(answers, embed_url=DEFAULT_EMBED_URL, dissent_threshold=0.75):
    texts = [a["answer"] if isinstance(a, dict) else str(a) for a in answers]
    texts = [t[:MAX_ANSWER] for t in texts]
    n = len(texts)
    if n == 0:
        return {"agreement": 0.0, "majority_answer": None, "dissenters": [], "method": "none"}
    if n == 1:
        return {"agreement": 1.0, "majority_answer": texts[0], "dissenters": [], "method": "single"}
    try:
        vecs = _embed(texts, embed_url)
        sim = lambda i, j: _cosine(vecs[i], vecs[j])
        method = "embeddings"
    except Exception:
        sim = lambda i, j: _jaccard(texts[i], texts[j])
        method = "jaccard"
    mean = []
    for i in range(n):
        s = [sim(i, j) for j in range(n) if j != i]
        mean.append(sum(s) / len(s))
    best = max(range(n), key=lambda i: mean[i])
    pair = [sim(i, j) for i in range(n) for j in range(i + 1, n)]
    agreement = max(0.0, min(1.0, sum(pair) / len(pair)))
    dissenters = [i for i in range(n) if i != best and sim(i, best) < dissent_threshold]
    names = [a.get("name", i) if isinstance(a, dict) else i for i, a in enumerate(answers)]
    return {"agreement": round(agreement, 4), "majority_answer": texts[best],
            "dissenters": [names[i] for i in dissenters], "method": method}


# ---------- review ----------
def extract_json(text):
    """Return first parseable JSON object found in noisy text, else None."""
    if not isinstance(text, str):
        return None
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def review(task_text, acceptance_text, candidate_answer, config_path, _advisors=None):
    advs = _advisors if _advisors is not None else load_config(config_path)
    advs = [a for a in advs if a.get("role") in REVIEW_ROLES]
    prompt = (f"TASK:\n{task_text}\n\nACCEPTANCE CRITERIA:\n{acceptance_text}\n\n"
              f"CANDIDATE ANSWER:\n{candidate_answer}\n\n"
              'Return strict JSON {"verdict":"pass"|"fail","reasons":[...]}.')
    raw = ask_advisors(prompt, config_path, system=REVIEW_SYSTEM, _advisors=advs)
    votes, reasons, details = [], [], []
    for r in raw:
        d = {"name": r["name"], "ok": r["ok"], "verdict": None}
        if r["ok"]:
            obj = extract_json(r["answer"])
            v = str(obj.get("verdict", "")).lower() if obj else ""
            if v in ("pass", "fail"):
                d["verdict"] = v
                votes.append(v)
                rs = obj.get("reasons", [])
                if isinstance(rs, list):
                    reasons += [f"{r['name']}: {str(x)[:500]}" for x in rs]
        details.append(d)
    n_pass, n_fail = votes.count("pass"), votes.count("fail")
    if len(votes) < 2:
        verdict = "fail"
        reasons.insert(0, f"insufficient advisors answered ({len(votes)}<2)")
    else:
        verdict = "pass" if n_pass > n_fail else "fail"  # tie -> fail
    return {"verdict": verdict, "reasons": reasons, "votes": {"pass": n_pass, "fail": n_fail},
            "answered": len(votes), "advisors": details}


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description="NOX advisors")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("--config", required=True)
    a.add_argument("--system")
    a.add_argument("--embed-url", default=DEFAULT_EMBED_URL)
    r = sub.add_parser("review")
    r.add_argument("--task-file", required=True)
    r.add_argument("--acceptance-file", required=True)
    r.add_argument("--answer-file", required=True)
    r.add_argument("--config", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "ask":
        res = ask_advisors(args.question, args.config, args.system)
        out = {"answers": res,
               "consensus": consensus([x for x in res if x["ok"]], args.embed_url)}
    else:
        out = review(_read(args.task_file), _read(args.acceptance_file),
                     _read(args.answer_file), args.config)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
