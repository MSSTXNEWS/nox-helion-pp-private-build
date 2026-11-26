echo "C300: aud_s3"
date -u
cd /workspace/nox
echo "== who holds ports 8090 8301"; ss -tlnp 2>/dev/null | grep -E ":(8090|8301|8510|8104|8105|18091|8091) " | sed -E 's/users:\(\("([^"]+)",pid=([0-9]+).*/\1 \2/' | awk '{print $4,$NF,$(NF-1)}'
for p in $(pgrep -f "core_8090|nox_core|ops_core" | head -5); do echo "core-like $p $(ps -o etimes=,stat= -p $p) $(ps -o args= -p $p | cut -c1-90)"; done
tail -3 agent/out/core_8090.log | cut -c1-160
echo "== stopped llama"; ps -o pid,stat,etimes,rss,args -p 3638858 2>/dev/null | cut -c1-160
echo "== RSS top"; ps -eo pid,rss,stat,comm --sort=-rss | head -12 | awk '{printf "%s %.1fG %s %s\n",$1,$2/1048576,$3,$4}'
echo "== chrome parents"; for p in $(pgrep -f chrome-headless | head -40); do pp=$(ps -o ppid= -p $p); while [ -n "$pp" ] && [ "$pp" -gt 1 ] && ps -o comm= -p $pp | grep -q -E "chrome|node|headless"; do pp=$(ps -o ppid= -p $pp|tr -d ' '); done; echo "$(ps -o args= -p $pp 2>/dev/null | cut -c1-100)"; done | sort | uniq -c | head
echo "== web_server turn handling"
grep -a -n -E "api/turn" agent/out/web_server.log | tail -5 | sed -E 's/[A-Za-z0-9_-]{24,}/<X>/g' | cut -c1-200
grep -a -c "api/turn" agent/out/web_server.log
echo "-- adapter 8510 tail err context"
grep -a -B3 "BrokenPipeError" agent/out/adapter_chain_8510.log | grep -a -E "File|line" | sed -E 's/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -6 | cut -c1-200
echo "-- timings in adapter/web logs"
grep -a -o -E "(ttft|first_token|first|dt|elapsed|ms)[=: ]+[0-9.]+" agent/out/adapter_chain_8510.log | tail -20 | tr '\n' ' '; echo
echo "== chat diag"
CF=$(ls /workspace/nox/svc/caddy/Caddyfile /workspace/nox/Caddyfile /etc/caddy/Caddyfile 2>/dev/null | head -2); echo "caddyfiles: $CF"
for f in $CF; do grep -n -E "api/turn|handle_path /api|handle /api|reverse_proxy|:18091" $f | grep -v -i -E "key|token|auth" | head -20; done
B='{"conversation_id":"qa-audit-diag-'$(date +%s)'","message":"привет","mode":"fast"}'
for u in http://127.0.0.1:18091/api/turn http://127.0.0.1:8091/api/turn http://127.0.0.1:8090/api/turn; do
 curl -s -N -m 45 -o /tmp/aud_t.out -w "$u code=%{http_code} ttfb=%{time_starttransfer} total=%{time_total}\n" -H 'Content-Type: application/json' -d "$B" $u; echo "  bytes=$(wc -c </tmp/aud_t.out) events=$(grep -o '"type": *"[a-z]*"' /tmp/aud_t.out | sort | uniq -c | tr '\n' ' ')"; done
curl -s -m 30 -o /dev/null -w "8510 chat code=%{http_code} t=%{time_total}\n" -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"max_tokens":20}' http://127.0.0.1:8510/v1/chat/completions
curl -s -m 30 -o /dev/null -w "8104 direct code=%{http_code} t=%{time_total}\n" -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"max_tokens":20}' http://127.0.0.1:8104/v1/chat/completions
curl -s -m 5 http://127.0.0.1:8104/slots 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print('8104 slots',[(s.get('id'),s.get('is_processing'),s.get('n_ctx')) for s in d])" 2>&1 | head -2
tail -c 2000 agent/out/web_server.log | grep -a -v -i -E "token|key" | tail -8 | cut -c1-200
echo "== training detail"
R=agent/autotrain/rounds; for r in r036 r037 r038 r039; do ls $R/$r | tr '\n' ' ' | cut -c1-300; echo; done
for r in r036 r037 r038; do echo "-- $r"; for f in $R/$r/*.json; do python3 - "$f" <<'PY'
import json,sys
try:
  d=json.load(open(sys.argv[1]))
  def flat(d,p=""):
    out=[]
    if isinstance(d,dict):
      for k,v in d.items(): out+=flat(v,p+k+".")
    elif isinstance(d,(int,float,str,bool)) and len(str(d))<60: out.append((p[:-1],d))
    return out
  f=[x for x in flat(d) if any(s in x[0].lower() for s in ("hold","accept","verdict","decision","gate","fid","soul","score","init","best","reason","pass"))]
  print(sys.argv[1].split('/')[-1], f[:14])
except Exception as e: print(sys.argv[1].split('/')[-1],"ERR",e)
PY
done; done 2>/dev/null | cut -c1-600
echo "-- init adapter / phase"
grep -a -o -E "(init[-_ ]adapter|init|старт с|from)[^ ]{0,3} [^ ]*ckpt[^ ]*" agent/out/autotrain.log | tail -4
ls agent/autotrain/ | head -30 | tr '\n' ' '; echo
cat agent/autotrain/phase* 2>/dev/null | head -c 600; echo
ls -la --time-style=+%m-%dT%H:%M distill_v2/ckpt_keep | tail -15 | cut -c40-200
grep -a -h -o -E "ворот[^\n]{0,160}" agent/out/autotrain.log | tail -8
echo "== gates last"
ls -t ops/dpo/gates_*.json 2>/dev/null | head -3
echo "== owner_active log tail"; tail -5 state/orch/owner_active.log | cut -c1-200
echo "== cron lines (cmds only)"; crontab -l 2>/dev/null | grep -v '^#' | awk '{c=""; for(i=6;i<=NF;i++) c=c" "$i; print $1,$2,$3,$4,$5, substr(c,1,90)}' | sed -E 's/[A-Za-z0-9_-]{30,}/<X>/g'
echo "== tunnels"; pgrep -af "cloudflared|ssh .*-R|ssh .*-L" | sed -E 's/[A-Za-z0-9_=.-]{30,}/<X>/g' | cut -c1-150 | head
echo END
