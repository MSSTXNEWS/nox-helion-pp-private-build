echo "C300: aud_s4"
date -u; uptime
cd /workspace/nox
echo "== 8104 clients"; ss -tnp 2>/dev/null | grep -E "127.0.0.1:8104 *$|:8104 " | grep -v "LISTEN" | grep -o -E 'pid=[0-9]+' | sort | uniq -c | while read c p; do pid=${p#pid=}; echo "$c $pid $(ps -o args= -p $pid | grep -o -E '[A-Za-z0-9_./-]+\.(py|sh)|llama-server|caddy' | head -2 | tr '\n' ' ')"; done
curl -s -m 5 http://127.0.0.1:8104/slots | python3 -c "import json,sys;d=json.load(sys.stdin);print([(s.get('id'),s.get('is_processing'),s.get('id_task'),(s.get('next_token') or [{}])[0].get('n_decoded') if isinstance(s.get('next_token'),list) else None) for s in d])" 2>&1 | head -2
echo "== 8104 cmd flags"; ps -o args= -p $(pgrep -f "llama-server.*--port 8104" | head -1) | grep -o -E -- "--(parallel|np|ctx-size|c|threads|t|n-gpu-layers|ngl|cache-reuse|slot[a-z-]*|jinja|fa|flash-attn|ub|batch-size)[ =]?[^ ]*" | tr '\n' ' '; echo
echo "== big python 3837719"; ps -o etimes=,args= -p 3837719 | grep -o -E '^ *[0-9]+|[A-Za-z0-9_./-]+\.py' | tr '\n' ' '; echo
echo "== who restarts core_8090"; grep -a -B2 "NOX CORE core-1" agent/out/core_8090.log | grep -a -o -E "^[0-9:T-]{8,19}" | tail -3; grep -l -E "core_8090|nox_core.py" stewards/*.sh stewards/*.py agent/*.sh ops/*.sh operators/*.sh 2>/dev/null | head
echo "== turn stream format"
B='{"conversation_id":"qa-audit-fmt-'$(date +%s)'","message":"2+2?","mode":"fast"}'
curl -s -N -m 60 -H 'Content-Type: application/json' -d "$B" http://127.0.0.1:18091/api/turn > /tmp/aud_f.out; python3 - <<'PY'
import json,re
s=open('/tmp/aud_f.out',encoding='utf8',errors='replace').read()
print('bytes',len(s))
for ln in s.splitlines()[:12]:
    try:
        o=json.loads(ln); print(' keys',sorted(o.keys())[:10], {k:(v if isinstance(v,(int,float,bool)) else str(v)[:40]) for k,v in o.items() if k in('type','t','event','error','status','reason','code','text','delta')})
    except Exception: print(' raw',ln[:100])
PY
curl -s -m 20 -H 'Content-Type: application/json' -d "$B" http://127.0.0.1:8091/api/turn | head -c 200; echo
echo "== gates json"
for f in $(ls -t ops/dpo/gates_*.json | head -2); do python3 -c "
import json,sys;d=json.load(open('$f'))
def fl(d,p=''):
  o=[]
  if isinstance(d,dict):
    for k,v in d.items(): o+=fl(v,p+k+'.')
  elif isinstance(d,(int,float,bool)) or (isinstance(d,str) and len(d)<30): o.append(p[:-1]+'='+str(d)[:12])
  return o
print('$f',fl(d)[:40])"; done
echo "== ckpt guard config"; grep -a -o -E "(steps|max_steps|lr|learning_rate|tok_budget|accum)[=: ]+[0-9.e-]+" agent/autotrain/rounds/r039/train.log | sort | uniq -c | head -12
grep -a -E "init|старт|адаптер" agent/autotrain/rounds/r039/train.log | head -5 | cut -c1-200
echo END
