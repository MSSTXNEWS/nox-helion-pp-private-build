#!/bin/bash
# Тюнинг DeepSeek: больше экспертов на GPU и контекст x2. Авто-откат при сбое/замедлении. Работает в фоне.
L=/root/nox/logs/tune.log
if [ "$1" != "bg" ]; then
  nohup setsid bash "$0" bg >/dev/null 2>&1 < /dev/null &
  sleep 2; echo "started bg; log=$L"; exit 0
fi
exec >>$L 2>&1; echo "=== $(date -u +%T) tune start"
F=$(grep -rl -- "--n-cpu-moe 35" /etc/supervisor/conf.d /opt/supervisor-scripts /root/nox/scripts 2>/dev/null | xargs grep -l 8098 2>/dev/null | head -1)
[ -z "$F" ] && { echo "no file found, abort"; exit 1; }
echo "file=$F"; cp -a "$F" "$F.bak_tune"
bench(){ curl -s -m 150 http://127.0.0.1:8098/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Count from 1 to 60 separated by commas."}],"max_tokens":200}' | python3 -c "import sys,json;t=json.load(sys.stdin).get('timings',{});print(round(t.get('predicted_per_second',0),1))" 2>/dev/null; }
BEFORE=$(bench); echo "before_tps=$BEFORE"
sed -i 's/--n-cpu-moe 35/--n-cpu-moe 31/; s/ -c 8192 / -c 16384 /' "$F"
supervisorctl reread >/dev/null; supervisorctl update >/dev/null
supervisorctl restart nox-ds41-8098 >/dev/null 2>&1
ok=0
for i in $(seq 1 60); do sleep 10; c=$(curl -s -m 4 -o /dev/null -w %{http_code} http://127.0.0.1:8098/health); [ "$c" = "200" ] && { ok=1; break; }; done
echo "health_ok=$ok after_s=$((i*10))"
AFTER=0; [ $ok = 1 ] && AFTER=$(bench); echo "after_tps=$AFTER"
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
GOOD=$(python3 -c "print(1 if float('${AFTER:-0}' or 0) >= float('${BEFORE:-0}' or 0)*0.97 and $ok==1 else 0)")
if [ "$GOOD" != "1" ]; then
  echo "ROLLBACK"; cp -a "$F.bak_tune" "$F"; supervisorctl reread >/dev/null; supervisorctl update >/dev/null; supervisorctl restart nox-ds41-8098 >/dev/null 2>&1
else echo "KEEP new settings"; fi
echo "=== done $(date -u +%T)"
