echo "C300: srv_k152"
N=/workspace/nox; S=$N/web/pkg/server; F=$S/chat_core.py
cd $N; date -u +%T
# 2) tok_budget откат (идущий r039 не трогаем; со следующего раунда 4096)
[ -f state/accel_tok_budget ] && mv state/accel_tok_budget state/accel_tok_budget.rolled_back_k1 && echo "tok_budget: accel_tok_budget отключён (откат: mv обратно)"
# 3) qa-хромы
pkill -f "ms-playwright" ; pkill -f "rv_chat.py"; sleep 1; pgrep -fa "chrome-headless|rv_chat" | grep -v pgrep | wc -l
# 1) chat_core.py
cp -n $F $F.bak_k1_fast_$(date +%Y%m%d)
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
if "k1_fast" in s: print("уже"); raise SystemExit
helper='''
# k1_fast: ход владельца/qa- -> прямой стрим с :8104 (без гонки/советников). Выключатель: state/chat_fast.off. Дедлайн первого текста 8 с, всего 45 с.
def _k1_fast_ok(cid):
    try:
        if os.path.exists("/workspace/nox/state/chat_fast.off"): return False
        if str(cid).startswith("qa-"): return True
        return time.time() - os.path.getmtime("/workspace/nox/state/orch/OWNER_ACTIVE") < 120
    except Exception:
        return False
def _k1_heavy_pids():
    r = []
    try:
        for d in os.listdir("/proc"):
            if d.isdigit():
                try: cl = open("/proc/%s/cmdline" % d, "rb").read().decode("utf-8", "replace")
                except Exception: continue
                if "llama-server" in cl and ("Qwen3-30B-A3B" in cl or "Thinking-2507" in cl): r.append(int(d))
    except Exception: pass
    return r
def _via_fast(t, text, up_text, history, on_delta, got):
    import http.client as _hc
    prev = {}
    for p in _k1_heavy_pids():
        try: prev[p] = os.getpriority(os.PRIO_PROCESS, p); os.setpriority(os.PRIO_PROCESS, p, 19)
        except Exception: pass
    t0 = time.time(); n = 0; status = "done"; err = None
    try:
        sysm = [m for m in history if m.get("role") == "system"][:2]
        rest = [m for m in history if m.get("role") != "system"][-6:]
        msgs = sysm + rest + [{"role": "user", "content": up_text}]
        body = {"model": "x", "messages": msgs, "stream": True, "max_tokens": 300 if len(str(text)) < 240 else 700, "temperature": 0.7, "chat_template_kwargs": {"enable_thinking": False}}
        c = _hc.HTTPConnection("127.0.0.1", 8104, timeout=8); t.conn = c
        try:
            c.request("POST", "/v1/chat/completions", body=json.dumps(body, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
            r = c.getresponse()
            while True:
                if t.stop: status = "stopped"; break
                if time.time() - t0 > 45: break
                try: l = r.readline()
                except Exception:
                    if n == 0: raise
                    break
                if not l: break
                if not l.startswith(b"data:"): continue
                d = l[5:].strip()
                if d == b"[DONE]": break
                try: j = json.loads(d)
                except Exception: continue
                v = ((j.get("choices") or [{}])[0].get("delta") or {}).get("content")
                if v:
                    n += 1; on_delta(v, None)
                    if n == 1: c.sock.settimeout(10)
        except Exception as e:
            if n == 0:
                on_delta("Прости, я сейчас отвечаю медленно: модель занята. Повтори вопрос через минуту.", None); err = "fast8104: %s" % str(e)[:80]
        try: c.close()
        except Exception: pass
    finally:
        for p, v in prev.items():
            try: os.setpriority(os.PRIO_PROCESS, p, v)
            except Exception: pass
    return {"state": "ok", "status": status, "err": None}
'''
a="def _pipe_after(text, ans, cid, body, lv, out):"
assert s.count(a)==1; s=s.replace(a, helper+"\n"+a)
b="    drawing = draw_request(text) is not None\n"
assert s.count(b)==1
ins=b+'''    if (not drawing) and _k1_fast_ok(cid) and not t.stop:   # k1_fast
        t.backend = "fast"; out({"t": "meta", "turn_id": t.id, "backend": "fast", "fallback": None})
        res = _via_fast(t, text, up_text, history, on_delta, got)
        used = "fast"; status, err = res["status"], res.get("err")
'''
s=s.replace(b,ins)
c="    if ok_rte and not t.stop:\n"
assert s.count(c)==1; s=s.replace(c,"    if ok_rte and used is None and not t.stop:\n")
d='("nox" if used in ("core", "rte") else None)'
assert s.count(d)==1; s=s.replace(d,'("nox" if used in ("core", "rte", "fast") else None)')
open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled || { cp $F.bak_k1_fast_$(date +%Y%m%d) $F; echo ОТКАТ-компиляция; exit 1; }
grep -n "^import\|^from" $F | head -5 | cut -c1-100
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); echo web pid $pid
python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -2
cat > /tmp/k1p2.py <<'PY'
import json,time,sys,http.client
cid="qa-k1fast-%d"%int(time.time()); q=sys.argv[1] if len(sys.argv)>1 else "Привет, NOX! Как дела?"
t0=time.time(); c=http.client.HTTPConnection("127.0.0.1",18091,timeout=70)
c.request("POST","/api/turn",body=json.dumps({"conversation_id":cid,"message":q},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"})
r=c.getresponse(); ev=[]; txt=""
while True:
    l=r.readline()
    if not l: break
    try: o=json.loads(l)
    except Exception: continue
    tp=o.get("t")
    if tp=="delta":
        if not txt: ev.append(("первый текст",round(time.time()-t0,2)))
        txt+=o.get("text","")
    elif tp in("done","error"): ev.append((tp,round(time.time()-t0,2),o.get("backend"))); break
    elif tp in("stage",): ev.append((tp,round(time.time()-t0,2)))
print(ev, "|", txt[:120].replace("\n"," "))
PY
sleep 3; timeout 80 python3 /tmp/k1p2.py
