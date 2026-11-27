echo "K1: l2_mem_dep7"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
F=$N/web/pkg/server/chat_core.py
cp -n $F $F.bak_l2_s03
cat > /tmp/patch_chat_l2.py <<'PYEOF'
F = "/workspace/nox/web/pkg/server/chat_core.py"; s = open(F).read()
if "S03_RECALL" in s:
    print("already patched")
else:
    a = "def _living_pre(text, cid, body):"; b = "def _living_post(text, ans, cid, body):"
    assert s.count(a) == 1 and s.count(b) == 1
    s = s.replace(a, "def _living_pre0(text, cid, body):").replace(b, "def _living_post0(text, ans, cid, body):")
    add = '''# ---- S03_RECALL (LANE2, 27.11): recall top-k из s03.db (mem0+bge-m3+bge-reranker) перед ответом, запись фактов после хода; сервис :18220, таймаут 0.25 с; откат: touch state/s03_recall.off или chat_core.py.bak_l2_s03 ----
def _s03_user(cid, body):
    return str(body.get("user_id") or body.get("nox_user_id") or ("qa-" + str(cid)[:40] if str(cid).startswith("qa-") else "owner"))[:64]
def _s03_on(text):
    return not (os.path.exists("/workspace/nox/state/s03_recall.off") or str(text).startswith("/"))
def _living_pre(text, cid, body):
    r = _living_pre0(text, cid, body)
    try:
        if r.get("reply") is not None or not _s03_on(text): return r
        m = _living_call_t("http://127.0.0.1:18220/recall", {"q": text, "cid": cid, "user": _s03_user(cid, body), "incognito": bool(body.get("nox_incognito") or body.get("incognito"))}, 0.25)
        c = (m or {}).get("context")
        if c:
            r = dict(r or {}); r["context"] = ((r.get("context") or "") + "\\n\\n" + c).strip()
            mt = dict(r.get("meta") or {}); mt["s03_hits"] = m.get("hits"); mt["s03_ms"] = m.get("ms"); r["meta"] = mt
    except Exception: pass
    return r
def _living_post(text, ans, cid, body):
    _living_post0(text, ans, cid, body)
    try:
        if _s03_on(text) and ans:
            threading.Thread(target=_living_call_t, args=("http://127.0.0.1:18220/remember", {"text": text, "answer": ans[:300], "cid": cid, "user": _s03_user(cid, body), "incognito": bool(body.get("nox_incognito") or body.get("incognito"))}, 2.0), daemon=True).start()
    except Exception: pass

'''
    k = "# ---- C: конвейер ответа"
    assert s.count(k) == 1
    s = s.replace(k, add + k)
    open(F, "w").write(s); print("patched")
PYEOF
python3 /tmp/patch_chat_l2.py
python3 -m py_compile $F && echo compiled || { cp $F.bak_l2_s03 $F; echo ROLLED_BACK; }
ls /tmp/relaunch.py /tmp/k1p2.py 2>&1 | head -2
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 20; head -c 1800 /tmp/k1p2.py
