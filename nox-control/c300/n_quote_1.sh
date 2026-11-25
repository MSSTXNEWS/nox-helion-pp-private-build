echo "C300: n_quote_1"; cd /workspace/nox
W=web/pkg/server; [ -f $W/chat_core.py.bak_n_2 ] || cp $W/chat_core.py $W/chat_core.py.bak_n_2
cat > /tmp/n_pq.py <<'EOFP'
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
if "_living_quote" in s: print("already"); raise SystemExit
h='''def _living_quote(body, cid):
    if not _le("quote"): return ""
    try:
        q = str(body.get("quote") or "").strip()[:600]; rt = body.get("reply_to")
        if not q and isinstance(rt, dict) and isinstance(rt.get("index"), int):
            ms = load_conv(cid, create=False)["messages"]
            if 0 <= rt["index"] < len(ms): q = str(ms[rt["index"]].get("content") or "")[:600]
        return ("Пользователь отвечает на цитату: «%s». Учти её в ответе." % q) if q else ""
    except Exception: return ""
'''
a="def run_turn(body, emit):"; s=s.replace(a,h+a,1)
b="    _lv = _living_pre(text, cid, body)\n"
assert b in s
s=s.replace(b,b+'''    _qc = _living_quote(body, cid)
    if _qc: _lv = dict(_lv); _lv["context"] = (_qc + "\\n" + (_lv.get("context") or "")).strip()
''',1)
open(p,"w",encoding="utf-8").write(s); print("patched")
EOFP
python3 - <<'P'
import json;p='/workspace/nox/state/persona.json';d=json.load(open(p));d['living_engines']=dict(d.get('living_engines') or {},quote=True);json.dump(d,open(p,'w'),ensure_ascii=False,indent=1);print(d['living_engines'])
P
python3 /tmp/n_pq.py && python3 -m py_compile $W/chat_core.py && echo compile_ok
( $W/run_web.sh restart </dev/null >/tmp/n_web_restart.log 2>&1 ); sleep 8
rm -f /tmp/n_out.txt
cat > /tmp/n_t.py <<'EOFT'
import sys,json,urllib.request,time
msg,cid,tmo,extra=sys.argv[1],sys.argv[2],int(sys.argv[3]),json.loads(sys.argv[4])
b=dict({"conversation_id":cid,"message":msg},**extra)
rq=urllib.request.Request("http://127.0.0.1:8091/api/turn",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"})
t=time.time()
try:
    r=urllib.request.urlopen(rq,timeout=tmo); out=[]
    for l in r:
        l=l.decode("utf-8","replace").strip()
        if l: out.append(l[:260])
        if '"done"' in l: break
    print(r.status,"|".join(out)[:700])
except Exception as e: print("ERR",str(e)[:300])
EOFT
python3 /tmp/n_t.py "/память" nq1 30 '{"quote":"тест цитаты"}' | tee -a /tmp/n_out.txt
python3 /tmp/n_t.py "Ответь одним словом: ок" nq2 120 '{"quote":"Хочешь плана на завтра?"}' | tee -a /tmp/n_out.txt
python3 /tmp/n_t.py "Привет" nq3 120 '{"reply_to":{"index":0},"nox_incognito":true}' | tee -a /tmp/n_out.txt
if [ $(grep -c '"t": "done"' /tmp/n_out.txt) -ge 3 ]; then echo QUOTE_OK; else echo "QUOTE_FAIL -> rollback"; cp $W/chat_core.py.bak_n_2 $W/chat_core.py; ( $W/run_web.sh restart </dev/null >/tmp/n_web_restart.log 2>&1 ); fi
