"""judge_run: small-model judge returning a JSON verdict."""
import registry as R

SYSTEM = ('You are a strict judge. Reply ONLY with JSON: {"verdict":"pass"|"fail","score":0..1,"reasons":["..."]}. '
          "Pass only if the answer fully satisfies the criteria.")


@R.register("judge_run", "read", {"properties": {
    "task": {"type": "string"}, "answer": {"type": "string"}, "criteria": {"type": "string"},
    "endpoint": {"type": "string", "default": "http://127.0.0.1:8098"}, "model": {"type": "string", "default": "default"},
    "timeout": {"type": "integer", "default": 120}}, "required": ["task", "answer", "criteria"]},
    "Ask a small model (OpenAI-compatible endpoint) to judge answer vs criteria; returns parsed JSON verdict.")
def judge_run(a):
    prompt = "TASK:\n%s\n\nCRITERIA:\n%s\n\nANSWER:\n%s" % (a["task"], a["criteria"], a["answer"])
    st, d = R.http_json(a["endpoint"].rstrip("/") + "/v1/chat/completions",
                        {"model": a["model"], "temperature": 0, "max_tokens": 400,
                         "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]},
                        timeout=a["timeout"])
    if st == 0:
        return R.blocked("judge endpoint unreachable: %s" % d, "start the model server at " + a["endpoint"])
    if st != 200:
        return R.fail("endpoint HTTP %s: %s" % (st, str(d)[:150]))
    try:
        txt = d["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return R.fail("unexpected response shape")
    v = R.extract_json(txt)
    if not isinstance(v, dict) or v.get("verdict") not in ("pass", "fail"):
        return {"ok": False, "error": "judge returned no valid verdict", "raw": txt[:300]}
    return {"ok": True, "verdict": v["verdict"], "score": v.get("score"), "reasons": v.get("reasons", [])}
