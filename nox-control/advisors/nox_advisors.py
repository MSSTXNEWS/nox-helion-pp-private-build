#!/usr/bin/env python3
"""NOX advisors: consult local and remote OpenAI-compatible endpoints, allowlisted CLIs
(copilot/gemini) and SearXNG. Stdlib only. One brain: NOX stays the decider.

Advisor output is DATA: never executed, capped at MAX_ANSWER chars, labelled as
"мнение советника, не NOX". Keys come only from env (api_key_env), never from files/logs.
Outgoing text to remote advisors is filtered (secrets, local paths). Daily limits are
counted in a JSON file. Network: only URLs from the config and the embed URL.
"""
import argparse
import json
import math
import re
import sys
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
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


# ---------- safety: outgoing filter, key scrub, limits ----------
LABEL = "мнение советника, не NOX"
CLI_ALLOWLIST = {"copilot": ["copilot", "-p"], "gemini": ["gemini", "-p"]}
_SECRET_RES = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password|passwd|authorization)\b\s*[:=]\s*['\"]?(?:Bearer\s+)?[^\s'\",;]{6,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{16,}"),
]
_PATH_RES = [
    re.compile(r"(?<![\w.])(?:/(?:home|root|etc|var|opt|srv|mnt|tmp|usr|Users)/[^\s'\"`,;:)]*)"),
    re.compile(r"\b[A-Za-z]:\\[^\s'\"`,;:)]*"),
    re.compile(r"(?<![\w.])~/[^\s'\"`,;:)]*"),
]


def sanitize_outgoing(text):
    """Redact secrets and local filesystem paths before text leaves the machine."""
    n = 0
    for rx in _SECRET_RES:
        text, k = rx.subn("[REDACTED_SECRET]", text)
        n += k
    for rx in _PATH_RES:
        text, k = rx.subn("[PATH]", text)
        n += k
    return text, n


def _scrub(msg, secret):
    if secret and len(secret) >= 4:
        msg = msg.replace(secret, "***")
    msg, _ = sanitize_outgoing(msg)
    return msg


def _blocked(res, why, need):
    res["blocked"], res["need"], res["error"] = why, need, why
    return res


_STATE_LOCK = threading.Lock()


def state_path(config_path=None):
    p = os.environ.get("NOX_ADVISORS_STATE")
    if p:
        return p
    base = os.path.dirname(os.path.abspath(config_path)) if config_path else os.getcwd()
    return os.path.join(base, "advisors_usage.json")


def _today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def usage_take(path, name, limit, today=None):
    """Atomically count one call for today. Returns (allowed, used_after_or_current)."""
    today = today or _today()
    with _STATE_LOCK:
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
            if not isinstance(st, dict):
                st = {}
        except (OSError, ValueError):
            st = {}
        day = st.get(today, {}) if isinstance(st.get(today), dict) else {}
        used = int(day.get(name, 0))
        if limit is not None and used >= int(limit):
            return False, used
        day[name] = used + 1
        st = {today: day}  # drop older days
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, path)
        return True, used + 1


def _post_json(url, payload, timeout, headers=None):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _get_json(url, timeout):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _chat_url(base):
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if re.search(r"/v\d+$", base):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _retryable(e):
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (408, 429, 500, 502, 503, 504)
    return isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, OSError))


def _with_retries(fn, retries, sleep=time.sleep):
    for i in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            if i >= retries or not _retryable(e):
                raise
            sleep(min(8.0, 0.5 * 2 ** i))


def _run_cli(adv, prompt, timeout):
    """Allowlisted CLI advisor (copilot/gemini): no shell, empty temp cwd, minimal env."""
    tool = adv.get("cli")
    if tool not in CLI_ALLOWLIST:
        raise ValueError(f"cli not in allowlist: {tool!r}")
    exe = shutil.which(CLI_ALLOWLIST[tool][0])
    if not exe:
        raise FileNotFoundError(tool)
    env = {k: v for k, v in os.environ.items()
           if k in ("PATH", "HOME", "USER", "LANG", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
                    "XDG_CACHE_HOME", "GEMINI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN")}
    with tempfile.TemporaryDirectory() as cwd:  # read-only intent: nothing of ours to touch
        p = subprocess.run([exe] + CLI_ALLOWLIST[tool][1:] + [prompt], cwd=cwd, env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=timeout, shell=False)
    if p.returncode != 0:
        raise RuntimeError(f"{tool} exit {p.returncode}: {(p.stderr or '')[:300]}")
    return p.stdout


def _search_searxng(adv, query, timeout):
    base = adv["url"].rstrip("/")
    data = _get_json(f"{base}/search?format=json&q={urllib.parse.quote(query[:500])}", timeout)
    rows = []
    for r in (data.get("results") or [])[: int(adv.get("max_results", 5))]:
        rows.append(f"- {r.get('title', '')} | {r.get('url', '')} | {str(r.get('content', ''))[:300]}")
    return "\n".join(rows) or "(нет результатов)"


def _ask_one(adv, question, system, _state=None, _sleep=time.sleep):
    t0 = time.monotonic()
    name = adv.get("name", "?")
    kind = adv.get("kind", "openai")
    res = {"name": name, "ok": False, "answer": "", "latency_s": 0.0, "error": None,
           "role": adv.get("role"), "kind": kind, "label": LABEL}
    key = ""
    try:
        timeout = float(adv.get("timeout_s", 60))
        remote = kind != "openai" or bool(adv.get("api_key_env")) or bool(adv.get("remote"))
        question_out, redacted = (sanitize_outgoing(question) if remote else (question, 0))
        system_out = sanitize_outgoing(system)[0] if (remote and system) else system
        res["redacted"] = redacted
        if kind == "openai":
            env = adv.get("api_key_env")
            headers = {}
            if env:
                key = os.environ.get(env, "")
                if not key:
                    return _blocked(res, f"api key env {env} is not set",
                                    f"owner: export {env}=<key> in the NOX service environment")
                headers["Authorization"] = "Bearer " + key
            if not _admit(adv, _state, res):
                return res
            msgs = ([{"role": "system", "content": system_out}] if system_out else [])
            msgs.append({"role": "user", "content": question_out})
            payload = {"messages": msgs, "temperature": 0.2}
            if adv.get("model"):
                payload["model"] = adv["model"]
            data = _with_retries(lambda: _post_json(_chat_url(adv["url"]), payload, timeout, headers),
                                 int(adv.get("retries", 0)), _sleep)
            text = data["choices"][0]["message"]["content"]
            if not isinstance(text, str):
                raise ValueError("non-string content")
        elif kind == "cli":
            tool = adv.get("cli")
            if tool not in CLI_ALLOWLIST:
                return _blocked(res, f"cli {tool!r} not in allowlist", "use cli: copilot or gemini")
            if not shutil.which(CLI_ALLOWLIST[tool][0]):
                return _blocked(res, f"{tool} CLI not installed or not logged in",
                                f"owner: install {tool} CLI and sign in (GitHub/Google account)")
            if not _admit(adv, _state, res):
                return res
            prompt = (system_out + "\n\n" if system_out else "") + question_out
            text = _with_retries(lambda: _run_cli(adv, prompt, timeout),
                                 int(adv.get("retries", 0)), _sleep)
        elif kind == "searxng":
            if not _admit(adv, _state, res):
                return res
            text = _with_retries(lambda: _search_searxng(adv, question_out, timeout),
                                 int(adv.get("retries", 0)), _sleep)
        else:
            return _blocked(res, f"unknown kind {kind!r}", "use kind: openai|cli|searxng")
        text = str(text)[:MAX_ANSWER]
        res["answer"] = f"[{LABEL}: {name}] " + text if remote else text
        res["answer"] = res["answer"][:MAX_ANSWER]
        res["ok"] = True
    except subprocess.TimeoutExpired:
        res["error"] = "timeout"
    except Exception as e:  # dead/slow advisor must not break the call
        res["error"] = _scrub(f"{type(e).__name__}: {e}", key)[:500]
    res["latency_s"] = round(time.monotonic() - t0, 3)
    return res


def _admit(adv, state, res):
    """Daily limit gate. Counts the attempt. Returns False (and fills res) when exhausted."""
    limit = adv.get("daily_limit")
    if limit is None:
        return True
    ok, used = usage_take(state or state_path(), adv.get("name", "?"), limit)
    if not ok:
        _blocked(res, f"daily limit {limit} reached ({used} used today, UTC)",
                 "wait for the next UTC day or raise daily_limit in config")
        return False
    res["used_today"] = used
    return True


def ask_advisors(question, config_path, system=None, _advisors=None):
    advs = _advisors if _advisors is not None else load_config(config_path)
    advs = [a for a in (advs or []) if a.get("enabled", True)]
    if not advs:
        return []
    st = state_path(config_path)
    with ThreadPoolExecutor(max_workers=len(advs)) as ex:
        return list(ex.map(lambda a: _ask_one(a, question, system, st), advs))


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


CODE_SYSTEM = ("You are a code advisor. Reply with a minimal unified diff (---/+++/@@) "
               "in one fenced block, then at most 3 lines of rationale. Do not run anything.")


def extract_patch(text):
    """First unified-diff-looking block from text, else None."""
    if not isinstance(text, str):
        return None
    for m in re.finditer(r"```(?:diff|patch)?\n(.*?)```", text, re.S):
        if re.search(r"^--- .+\n\+\+\+ .+", m.group(1), re.M) and "@@" in m.group(1):
            return m.group(1).strip("\n") + "\n"
    m = re.search(r"^--- .+\n\+\+\+ .+\n@@.*", text, re.M | re.S)
    return text[m.start():].strip("\n") + "\n" if m else None


def code_consensus(task, config_path, embed_url=DEFAULT_EMBED_URL, _advisors=None):
    """ask -> compare -> patch PROPOSAL. Never applies anything."""
    raw = ask_advisors(task, config_path, system=CODE_SYSTEM, _advisors=_advisors)
    good = [r for r in raw if r["ok"] and r["kind"] != "searxng"]
    cons = consensus(good, embed_url)
    patches = {r["name"]: extract_patch(r["answer"]) for r in good}
    best = cons["majority_answer"]
    proposal = extract_patch(best) if best else None
    if len(good) < 2:
        status = "insufficient"
    elif proposal is None:
        status = "no_patch"
    else:
        status = "agree" if not cons["dissenters"] and cons["agreement"] >= 0.75 else "split"
    return {"status": status, "label": LABEL, "applied": False, "proposal": proposal,
            "agreement": cons["agreement"], "dissenters": cons["dissenters"],
            "method": cons["method"], "patches_found": sorted(k for k, v in patches.items() if v),
            "blocked": [{"name": r["name"], "blocked": r["blocked"], "need": r["need"]}
                        for r in raw if r.get("blocked")]}


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
    c = sub.add_parser("code")
    c.add_argument("task")
    c.add_argument("--config", required=True)
    c.add_argument("--embed-url", default=DEFAULT_EMBED_URL)
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
    elif args.cmd == "code":
        out = code_consensus(args.task, args.config, args.embed_url)
    else:
        out = review(_read(args.task_file), _read(args.acceptance_file),
                     _read(args.answer_file), args.config)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
