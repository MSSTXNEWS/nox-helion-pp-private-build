echo "K1: l1_slot5"
export RUNNER_TRACKING_ID=""
F=/workspace/nox/integration/adapter.py
[ -f $F.bak_l1_1 ] || cp $F $F.bak_l1_1
python3 - <<'P'
F="/workspace/nox/integration/adapter.py"
s=open(F).read()
if "L1_SLOT" in s: print("already"); raise SystemExit
helper='''
def _l1_slotify(raw):  # L1_SLOT 27.11: слот 0 :8104 зарезервирован за чатом, фон -> слоты 1-3
    try:
        import json as _j, random as _r
        o = _j.loads(raw)
        if isinstance(o, dict) and "messages" in o and "id_slot" not in o:
            o["id_slot"] = _r.choice((1, 2, 3)); o["cache_prompt"] = True
            return _j.dumps(o, ensure_ascii=False).encode("utf-8")
    except Exception:
        pass
    return raw

'''
a='def call(method, url, raw=None, timeout=10.0):\n'
assert a in s
s=s.replace(a,helper+a+'    if raw and isinstance(url, str) and url.startswith(BASE) and url.endswith("/chat/completions"): raw = _l1_slotify(raw)\n',1)
b='    def _proxy(self, base, raw):\n'
assert b in s
s=s.replace(b,b+'        if raw and base == BASE and self.path.endswith("/chat/completions"): raw = _l1_slotify(raw)\n',1)
open(F,"w").write(s); print("patched")
P
python3 -m py_compile $F && echo compile_ok || { cp $F.bak_l1_1 $F; echo ROLLBACK; exit 0; }
pid=$(ss -ltnp | grep ":8510 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
tr '\0' '\n' </proc/$pid/cmdline > /tmp/l1_adapter_cmd; cwd=$(readlink /proc/$pid/cwd)
tr '\0' '\0' </proc/$pid/environ > /tmp/l1_adapter_env
echo "old_pid_found=$([ -n "$pid" ] && echo yes || echo no)"
kill $pid; sleep 20
code=$(curl -s -m3 -o /dev/null -w %{http_code} localhost:8510/health); echo "adapter_after_kill=$code"
if [ "$code" != "200" ]; then
  cd $cwd; xargs -0 -a <(tr '\n' '\0' </tmp/l1_adapter_cmd) env -i $(cat /tmp/l1_adapter_env | tr '\0' '\n' | grep -E '^(PATH|HOME|NOX_)' | tr '\n' ' ') setsid nohup  >/dev/null 2>&1 &
  sleep 10; echo "adapter_restarted=$(curl -s -m3 -o /dev/null -w %{http_code} localhost:8510/health)"
fi
rm -f /tmp/l1_adapter_env
echo "== slots + test"
python3 - <<'P'
import json,time,urllib.request
print([(x['id'],int(x['is_processing'])) for x in json.load(urllib.request.urlopen("http://127.0.0.1:8104/slots"))])
for i in range(3):
  t0=time.time();b={"conversation_id":"qa-l1s-%d-%d"%(i,t0),"message":"Назови столицу Франции."}
  rq=urllib.request.Request("http://127.0.0.1:8091/api/turn",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"});first=None
  try:
    with urllib.request.urlopen(rq,timeout=60) as r:
      for l in r:
        l=l.decode().strip()
        try: j=json.loads(l[5:] if l.startswith("data:") else l)
        except Exception: continue
        if j.get("t")=="delta" and first is None: first=time.time()-t0
        if j.get("t") in("done","error"): break
  except Exception as e: print("EXC",type(e).__name__)
  print("ttft",first and round(first,2)); time.sleep(4)
P
