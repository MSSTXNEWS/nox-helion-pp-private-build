echo "K1: rs_deep"
export RUNNER_TRACKING_ID=""
W=/workspace/nox; C=$W/web/pkg/server/chat_core.py
grep -q "_deep_advisors" $C && { echo "already patched"; } || {
cp -a $C $C.bak_rsdeep_$(date +%s)
python3 - <<'PY'
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
fn='''_DEEP_ADV = ["groq/llama-3.3-70b-versatile", "cerebras/qwen-3-32b", "google/gemini-2.5-flash", "llm7/deepseek-v4.1-flash"]
def _deep_advisors(out, t, text, up_text, history, lv):
    # RS 27.11: режим «Глубоко» — советники через шлюз :8793, итог даёт NOX. Откат: touch state/deep_adv.off
    import concurrent.futures as cf, urllib.request as ur
    out({"t": "stage", "text": "советуюсь с советниками…", "code": "advisors"})
    h = [{"role": m["role"], "content": str(m.get("content") or "")[:500]} for m in history if m.get("role") in ("user", "assistant")][-4:]
    def one(m):
        try:
            rq = ur.Request("http://127.0.0.1:8793/v1/chat/completions", data=json.dumps({"model": m, "messages": h + [{"role": "user", "content": str(text)[:2000]}], "max_tokens": 350, "temperature": 0.4}).encode(), headers={"Content-Type": "application/json"})
            with ur.urlopen(rq, timeout=14) as r: j = json.loads(r.read())
            c = (((j.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
            return (m, c) if c else None
        except Exception: return None
    ex = cf.ThreadPoolExecutor(len(_DEEP_ADV)); fs = [ex.submit(one, m) for m in _DEEP_ADV]; res = []
    try:
        for f in cf.as_completed(fs, timeout=15):
            r = f.result()
            if r: res.append(r)
            if len(res) >= 3: break
    except Exception: pass
    ex.shutdown(wait=False)
    names = [m for m, _ in res]
    if not res:
        out({"t": "stage", "text": "советники не ответили, отвечаю сама…", "code": "advisors_unavailable"}); return up_text
    out({"t": "meta", "turn_id": t.id, "advisors": names}); out({"t": "stage", "text": "советники ответили: %d" % len(res), "code": "advisors_ok", "advisors": names})
    try: lv["meta"] = dict(lv.get("meta") or {}, advisors=names)
    except Exception: pass
    note = "[Мнения советников (сверь, не копируй; итоговый ответ дай сама, от первого лица):\\n" + "\\n".join("- %s: %s" % (m, c[:700]) for m, c in res) + "\\n]\\n\\n"
    return note + up_text
'''
a="def _via_fast("; assert s.count(a)==1; s=s.replace(a,fn+a)
b="        got[0] = True   # снять гонку/советников\n"; assert s.count(b)==1
s=s.replace(b,b+'        if mode == "deep" and not os.path.exists("/workspace/nox/state/deep_adv.off") and not str(text).startswith("/"):\n            try: up_text = _deep_advisors(out, t, text, up_text, history, _lv)\n            except Exception: pass\n')
open(p,"w",encoding="utf-8").write(s)
PY
python3 -m py_compile $C && echo compile_ok || { cp -a $(ls -t $C.bak_rsdeep_* | head -1) $C; echo REVERTED; }
}
grep -n "_lv = \|_lv=" $C | head -3 | cut -c1-120
head -12 $W/ops/relaunch.py | cut -c1-200
