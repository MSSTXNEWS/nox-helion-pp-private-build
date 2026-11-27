echo "K1: l1_chat2"
W=/workspace/nox/web/pkg/server; F=$W/chat_core.py
cp $F $F.bak_l1_2
python3 - <<'P'
F="/workspace/nox/web/pkg/server/chat_core.py"
s=open(F).read()
a='c = _hc.HTTPConnection("127.0.0.1", 8104, timeout=30); t.conn = c'
assert a in s
s=s.replace(a,'c = _hc.HTTPConnection("127.0.0.1", 8104, timeout=9); t.conn = c',1)
b='''            if n == 0:
                on_delta("Прости, я сейчас отвечаю медленно'''
assert b in s
rep='''            if n == 0 and not t.stop:   # L1: слот 0 занят -> один повтор на любой свободный слот
                try:
                    c.close()
                    b2 = dict(body); b2.pop("id_slot", None)
                    c = _hc.HTTPConnection("127.0.0.1", 8104, timeout=25); t.conn = c
                    c.request("POST", "/v1/chat/completions", body=json.dumps(b2, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
                    r = c.getresponse()
                    while time.time() - t0 < 44 and not t.stop:
                        l = r.readline()
                        if not l: break
                        if not l.startswith(b"data:"): continue
                        d = l[5:].strip()
                        if d == b"[DONE]": break
                        v = ((json.loads(d).get("choices") or [{}])[0].get("delta") or {}).get("content")
                        if v: n += 1; on_delta(v, None)
                except Exception: pass
            if n == 0:
                on_delta("Прости, я сейчас отвечаю медленно'''
s=s.replace(b,rep,1)
open(F,"w").write(s)
P
python3 -m py_compile $F && echo compile_ok || { cp $F.bak_l1_2 $F; echo ROLLBACK; exit 0; }
( $W/run_web.sh restart </dev/null >/tmp/l1_web_restart.log 2>&1 ); sleep 12
curl -s -m4 localhost:8104/slots | python3 -c "import json,sys;print([(x['id'],x['is_processing']) for x in json.load(sys.stdin)])"
for i in 1 2 3 4; do
python3 - <<'P'
import json,time,urllib.request
t0=time.time()
b={"conversation_id":"qa-l1-%d"%int(t0),"message":"Назови три цвета радуги."}
rq=urllib.request.Request("http://127.0.0.1:8091/api/turn",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"})
first=None;txt=""
try:
  with urllib.request.urlopen(rq,timeout=60) as r:
    for l in r:
      l=l.decode().strip()
      try: j=json.loads(l[5:] if l.startswith("data:") else l)
      except Exception: continue
      if j.get("t")=="delta":
        if first is None: first=time.time()-t0
        txt+=j.get("text","")
      if j.get("t") in("done","error"): break
except Exception as e: print("EXC",e)
print("ttft",first and round(first,2),"total",round(time.time()-t0,1),txt[:50])
P
sleep 3; done
