"""eval_gate: holdout score before/after + threshold gate."""
import json
import re
import registry as R


def judge_answer(case, ans):
    if "exact" in case:
        return ans.strip() == str(case["exact"]).strip()
    if "contains" in case:
        c = case["contains"]
        return all(x.lower() in ans.lower() for x in ([c] if isinstance(c, str) else c))
    if "regex" in case:
        return re.search(case["regex"], ans, re.S) is not None
    raise ValueError("case needs exact|contains|regex")


def load_cases(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


@R.register("eval_gate", "read", {"properties": {
    "action": {"type": "string", "enum": ["score", "gate"]},
    "holdout": {"type": "string", "description": "jsonl: {prompt, exact|contains|regex}"},
    "answers": {"type": "string", "description": "jsonl of {answer} per case (offline scoring)"},
    "endpoint": {"type": "string", "description": "OpenAI-compatible base url e.g. http://127.0.0.1:8098"},
    "model": {"type": "string", "default": "default"}, "timeout": {"type": "integer", "default": 120},
    "baseline": {"type": "number"}, "candidate": {"type": "number"}, "max_drop": {"type": "number", "default": 0.02},
    "min_score": {"type": "number", "default": 0.0}}, "required": ["action"]},
    "score: run holdout through endpoint or read answers file -> accuracy. gate: candidate >= baseline - max_drop and >= min_score.")
def eval_gate(a):
    if a["action"] == "gate":
        if a.get("baseline") is None or a.get("candidate") is None:
            return R.fail("baseline and candidate required")
        passed = a["candidate"] >= a["baseline"] - a["max_drop"] and a["candidate"] >= a["min_score"]
        return {"ok": True, "pass": passed, "baseline": a["baseline"], "candidate": a["candidate"],
                "delta": round(a["candidate"] - a["baseline"], 4), "max_drop": a["max_drop"]}
    if not a.get("holdout"):
        return R.fail("holdout required")
    cases = load_cases(R.safe_path(a["holdout"], must_exist=True))
    if not cases:
        return R.fail("empty holdout")
    answers = None
    if a.get("answers"):
        answers = [json.loads(l)["answer"] for l in open(R.safe_path(a["answers"], must_exist=True), encoding="utf-8") if l.strip()]
        if len(answers) != len(cases):
            return R.fail("answers count != cases count")
    elif not a.get("endpoint"):
        return R.blocked("no model endpoint or answers file", "pass endpoint (llama.cpp URL) or answers jsonl")
    ok_n, details = 0, []
    for i, c in enumerate(cases):
        if answers is not None:
            ans = answers[i]
        else:
            st, d = R.http_json(a["endpoint"].rstrip("/") + "/v1/chat/completions",
                                {"model": a["model"], "temperature": 0, "messages": [{"role": "user", "content": c["prompt"]}]},
                                timeout=a["timeout"])
            if st != 200:
                return R.blocked("endpoint unreachable/error (%s): %s" % (st, str(d)[:100]), "start the model server at " + a["endpoint"])
            ans = d["choices"][0]["message"]["content"]
        good = judge_answer(c, ans)
        ok_n += good
        details.append({"i": i, "pass": good})
    return {"ok": True, "n": len(cases), "passed": ok_n, "score": round(ok_n / len(cases), 4), "details": details[:200]}
