#!/bin/bash
# Проба: батч x2 (b 4096, ub 2048), слоты прежние. Мерит ген и чтение промпта. Авто-откат. Фон.
L=/root/nox/logs/tune3.log
if [ "$1" != "bg" ]; then
  nohup setsid bash "$0" bg >/dev/null 2>&1 < /dev/null &
  sleep 2; echo "started bg; log=$L"; exit 0
fi
exec >>$L 2>&1; echo "=== $(date -u +%T) tune3 start"
FILES="/etc/supervisor/conf.d/nox-ds41-8098.conf /root/nox/ops/nox_boot_ds41_8098.sh /root/nox/models/deepseek_v41_flash_iq2xxs/launch_ds41_8098_t119u.sh"
for f in $FILES; do [ -f "$f" ] && { [ -f "$f.bak_t3" ] || cp -a "$f" "$f.bak_t3"; echo "== $f"; grep -nE -- '-np |-c [0-9]|-b [0-9]|-ub |NP=|N_CPU_MOE|CTX' "$f" | cut -c1-220; }; done
bench(){ P=$(python3 -c "print('Расскажи кратко о Москве. '*55)"); curl -s -m 170 http://127.0.0.1:8098/v1/chat/completions -H 'Content-Type: application/json' -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$P\"}],\"max_tokens\":60,\"cache_prompt\":false}" | python3 -c "import sys,json;t=json.load(sys.stdin).get('timings',{});print(round(t.get('predicted_per_second',0),1),round(t.get('prompt_per_second',0),1))" 2>/dev/null; }
BEFORE=$(bench); echo "before_tps=$BEFORE"
for f in $FILES; do [ -f "$f" ] && sed -i -E 's/\$\{B:-2048\}/${B:-4096}/; s/\$\{UB:-1024\}/${UB:-2048}/' "$f"; done
supervisorctl reread >/dev/null; supervisorctl update >/dev/null
supervisorctl restart nox-ds41-8098 >/dev/null 2>&1
ok=0
for i in $(seq 1 180); do sleep 10; c=$(curl -s -m 4 -o /dev/null -w %{http_code} http://127.0.0.1:8098/health); [ "$c" = "200" ] && { ok=1; break; }; done
echo "health_ok=$ok after_s=$((i*10))"
AFTER=0; [ $ok = 1 ] && AFTER=$(bench); echo "after_tps=$AFTER"
ps -eo args | grep -E 'llama-server|server' | grep -E -- '-np|--parallel' | head -1 | cut -c1-500
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
GEN_B=${BEFORE% *}; PR_B=${BEFORE#* }; GEN_A=${AFTER% *}; PR_A=${AFTER#* }
GOOD=$(python3 -c "print(1 if float('${GEN_A:-0}')>=float('${GEN_B:-0}')*0.95 and float('${PR_A:-0}')>=float('${PR_B:-1}')*1.2 and $ok==1 else 0)")
if [ "$GOOD" != "1" ]; then
  echo "ROLLBACK"; for f in $FILES; do [ -f "$f.bak_t3" ] && cp -a "$f.bak_t3" "$f"; done; supervisorctl reread >/dev/null; supervisorctl update >/dev/null; supervisorctl restart nox-ds41-8098 >/dev/null 2>&1
else echo "KEEP new settings"; fi
echo "=== done $(date -u +%T)"
