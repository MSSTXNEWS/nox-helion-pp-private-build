echo "C300: n_chat_3"
cd /workspace/nox
echo "=== ENABLE FLAGS + PATCH CHAT"
python3 - <<'P'
import json;p='/workspace/nox/state/persona.json';d=json.load(open(p));d['living_engines']=dict(d.get('living_engines') or {},mem0=True,emotion=True,rituals=True);json.dump(d,open(p,'w'),ensure_ascii=False,indent=1);print(d['living_engines'])
P
W=/workspace/nox/web/pkg/server
[ -f $W/chat_core.py.bak_n_1 ] || cp $W/chat_core.py $W/chat_core.py.bak_n_1
cat > /tmp/n_patch_chat.py <<'EOFP'
import re,sys
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
if "_living_pre" in s: print("already patched"); sys.exit(0)
helpers='''# ---- N: движки живого ИИ (память, эмоции, команды) -> сервис 127.0.0.1:18215; флаги persona.json: living_engines; откат: chat_core.py.bak_n_1 ----
def _le(name):
    try:
        with open("/workspace/nox/state/persona.json", encoding="utf-8") as f: d = json.load(f)
        return bool((d.get("living_engines") or {}).get(name))
    except Exception: return False
def _living_call(path, obj, timeout=4.0):
    try:
        import urllib.request as _ur
        rq = _ur.Request("http://127.0.0.1:18215" + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
        with _ur.urlopen(rq, timeout=timeout) as r: return json.loads(r.read())
    except Exception: return {}
def _living_pre(text, cid, body):
    if not (_le("mem0") or _le("emotion")): return {}
    inc = bool(body.get("nox_incognito") or body.get("incognito"))
    r = _living_call("/pre", {"text": text, "cid": cid, "incognito": inc, "mem": _le("mem0"), "emo": _le("emotion")})
    return r if isinstance(r, dict) else {}
def _living_ctx(lv):
    c = (lv or {}).get("context")
    return [{"role": "system", "content": c}] if c else []
def _living_post(text, ans, cid, body):
    if _le("mem0") or _le("emotion"):
        __import__("threading").Thread(target=_living_call, args=("/post", {"text": text, "answer": ans[:500], "cid": cid}, 2.0), daemon=True).start()

'''
a="def run_turn(body, emit):"
assert a in s; s=s.replace(a,helpers+a,1)
b='    with LOCK:\n        conv = load_conv(cid)\n        if running_turn(cid):'
assert b in s
sc='''    _lv = _living_pre(text, cid, body)
    if _lv.get("reply") is not None:      # N: /команды памяти и режимов отвечает сервис без модели
        with LOCK:
            conv = load_conv(cid); _now = time.time()
            conv["messages"].append({"id": "m-" + uuid.uuid4().hex[:10], "role": "user", "content": text, "ts": _now, "source": source})
            conv["messages"].append({"id": "m-" + uuid.uuid4().hex[:10], "role": "assistant", "content": str(_lv["reply"]), "ts": _now + 0.01, "source": source, "status": "done", "backend": "living", "meta": _lv.get("meta")})
            save_conv(conv)
        emit({"t": "meta", "conversation_id": cid, "backend": "living"}); emit({"t": "delta", "text": str(_lv["reply"])})
        emit({"t": "done", "status": "done", "backend": "living", "meta": _lv.get("meta"), "n": len(conv["messages"])})
        return
'''
s=s.replace(b,sc+b,1)
c="        history = _persona_prefix() + history"
assert c in s; s=s.replace(c,"        history = _persona_prefix() + _living_ctx(_lv) + history",1)
d='"status": status, "mode": mode, "path": info.get("path")})'
assert d in s; s=s.replace(d,'"status": status, "mode": mode, "path": info.get("path"), "meta": _lv.get("meta")})',1)
e="    t.drop()\n    if err and status == \"error\":"
assert e in s; s=s.replace(e,"    t.drop()\n    _living_post(text, ans, cid, body)\n    if err and status == \"error\":",1)
f='"path": info.get("path"), "mode": mode, "n": len(conv["messages"])})'
assert f in s; s=s.replace(f,'"path": info.get("path"), "mode": mode, "n": len(conv["messages"]), "meta": _lv.get("meta")})',1)
open(p,"w",encoding="utf-8").write(s); print("patched")
EOFP
python3 /tmp/n_patch_chat.py && python3 -m py_compile $W/chat_core.py && echo compile_ok
grep -n "^PORT\|PORT =" $W/web_server.py | head -3
grep -n "run_web\|restart" $W/run_web.sh | head -5
( $W/run_web.sh restart </dev/null >/tmp/n_web_restart.log 2>&1 ) ; sleep 8; tail -3 /tmp/n_web_restart.log
WP=$(grep -o "PORT = [0-9]*\|PORT\", \"[0-9]*" $W/web_server.py | head -1 | grep -o "[0-9]*$"); echo webport=$WP
rm -f /tmp/n_out.txt; cat > /tmp/n_t.py <<'EOFT'
import sys,json,urllib.request,time
port,path,msg,cid,tmo=sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5])
b=json.dumps({"conversation_id":cid,"message":msg,"text":msg,"prompt":msg}).encode()
rq=urllib.request.Request("http://127.0.0.1:%s%s"%(port,path),data=b,headers={"Content-Type":"application/json"})
t=time.time()
try:
    r=urllib.request.urlopen(rq,timeout=tmo); out=[]
    for l in r:
        l=l.decode("utf-8","replace").strip()
        if l: out.append(l[:300])
        if '"done"' in l or time.time()-t>tmo: break
    print(path,r.status,"|".join(out)[:900])
except Exception as e: print(path,"ERR",str(e)[:300], getattr(e,"read",lambda:b"")()[:200])
EOFT
P=8091
python3 /tmp/n_t.py $P /api/turn "/запомни Тестовая запись N" ntest1 30 | tee -a /tmp/n_out.txt
python3 /tmp/n_t.py $P /api/turn "/память" ntest1 30 | tee -a /tmp/n_out.txt
curl -s -m 10 -X POST 127.0.0.1:$P/api/feedback -H 'Content-Type: application/json' -d '{"rating":1,"conversation_id":"ntest1","answer":"x"}' | head -c 300; echo
python3 /tmp/n_t.py $P /api/turn "Привет! Ответь одним словом: ок" ntest2 150 | tee -a /tmp/n_out.txt
python3 /tmp/n_t.py $P /api/turn "/забудь_всё да" ntest1 30 | tee -a /tmp/n_out.txt

if grep -q "Тестовая запись" /tmp/n_out.txt && grep -q '"t": "done"' /tmp/n_out.txt; then echo "CHAT_OK"; else echo "CHAT_FAIL -> rollback"; cp $W/chat_core.py.bak_n_1 $W/chat_core.py; ( $W/run_web.sh restart </dev/null >/tmp/n_web_restart.log 2>&1 ); fi
df -BG /workspace | tail -1
