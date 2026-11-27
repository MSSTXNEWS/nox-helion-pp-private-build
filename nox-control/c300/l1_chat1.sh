echo "K1: l1_chat1"
export RUNNER_TRACKING_ID=""
W=/workspace/nox/web/pkg/server; F=$W/chat_core.py
[ -f $F.bak_l1_1 ] || cp $F $F.bak_l1_1
python3 - <<'P'
F="/workspace/nox/web/pkg/server/chat_core.py"
s=open(F).read()
if "L1_DEADLINE" in s: print("already"); raise SystemExit
a='    out({"t": "meta", "turn_id": t.id, "conversation_id": cid, "mode": mode, "length": length})\n'
assert a in s
add=a+'''    _fin = [False]   # L1_DEADLINE (27.11): финальный дедлайн 45 с и филлер
    def _l1_deadline():
        time.sleep(45)
        if not _fin[0] and alive[0]:
            out({"t": "error", "error": "ответ не успел за 45 с, повтори вопрос", "code": "deadline", "turn_id": t.id, "partial": bool(parts)})
            alive[0] = False
            try: stop(turn_id=t.id)
            except Exception: pass
    def _l1_filler():
        time.sleep(1.5)
        if not got[0] and not t.stop and not _fin[0]:
            out({"t": "stage", "text": "секунду…", "code": "filler"})
    threading.Thread(target=_l1_deadline, daemon=True).start()
    threading.Thread(target=_l1_filler, daemon=True).start()
'''
s=s.replace(a,add,1)
b='    t.drop()\n    _living_post(text, ans, cid, body)\n'
assert b in s
s=s.replace(b,'    _fin[0] = True\n'+b,1)
# DRY + прямой фолбэк
c='"id_slot": 0, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}\n        c = _hc'
assert c in s
s=s.replace(c,'"id_slot": 0, "cache_prompt": True, "dry_multiplier": 0.5, "dry_base": 1.75, "dry_allowed_length": 3, "chat_template_kwargs": {"enable_thinking": False}}\n        c = _hc',1)
# 8 c: сначала прямой :8104, затем советник
d='            out({"t": "stage", "text": "локальная модель думает долго, спрашиваю советника…"})\n            t1 = time.time(); r = _living_call_t("http://127.0.0.1:18217/fast", {"q": text, "history": h}, 14.0); txt = (r or {}).get("text")\n            if not txt:\n'
assert d in s
e='            out({"t": "stage", "text": "локальная модель думает долго, отвечаю напрямую…"})\n            t1 = time.time(); r = _p3_direct8104(text, h); txt = (r or {}).get("text")   # L1: сначала прямой :8104\n            if not txt:\n                r = _living_call_t("http://127.0.0.1:18217/fast", {"q": text, "history": h}, 14.0); txt = (r or {}).get("text")\n            if not txt:\n'
s=s.replace(d,e,1)
s=s.replace('float(body.get("race_s") or _le_num("race_s", 7.0))','float(body.get("race_s") or _le_num("race_s", 8.0))',1)
open(F,"w").write(s); print("patched")
P
python3 -m py_compile $F && echo compile_ok || { cp $F.bak_l1_1 $F; echo ROLLBACK; exit 0; }
( $W/run_web.sh restart </dev/null >/tmp/l1_web_restart.log 2>&1 ); sleep 12
echo "== test qa-"
for i in 1 2 3; do
python3 - <<'P'
import json,time,urllib.request
t0=time.time()
b={"conversation_id":"qa-l1-%d"%int(t0),"message":"Скажи одним предложением, что такое радуга."}
rq=urllib.request.Request("http://127.0.0.1:8091/api/turn",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"})
first=None;ev=[];txt=""
try:
  with urllib.request.urlopen(rq,timeout=60) as r:
    for l in r:
      l=l.decode("utf-8","replace").strip()
      if not l: continue
      try: j=json.loads(l[5:] if l.startswith("data:") else l)
      except Exception: continue
      ev.append(j.get("t"))
      if j.get("t")=="delta":
        if first is None: first=time.time()-t0
        txt+=j.get("text","")
      if j.get("t") in("done","error"): break
except Exception as e: print("EXC",type(e).__name__)
print("ttft=%s total=%.1f ev=%s txt=%s"%(None if first is None else round(first,2),time.time()-t0,",".join(dict.fromkeys(map(str,ev))),txt[:70]))
P
sleep 5
done
tail -4 /workspace/nox/state/chat_fast.log
