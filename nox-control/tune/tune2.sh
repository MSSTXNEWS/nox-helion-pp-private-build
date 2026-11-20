#!/bin/bash
# Пакет ускорения: 4 слота (чат+исполнители параллельно), контекст x2 (на слот прежний), батч x2 (быстрее чтение запроса). Авто-откат. Фон.
L=/root/nox/logs/tune2.log
if [ "$1" != "bg" ]; then
  nohup setsid bash "$0" bg >/dev/null 2>&1 < /dev/null &
  sleep 2; echo "started bg; log=$L"; exit 0
fi
exec >>$L 2>&1; echo "=== $(date -u +%T) tune2 start"
FILES="/etc/supervisor/conf.d/nox-ds41-8098.conf /root/nox/ops/nox_boot_ds41_8098.sh /root/nox/models/deepseek_v41_flash_iq2xxs/launch_ds41_8098_t119u.sh"
for f in $FILES; do [ -f "$f" ] && { [ -f "$f.bak_t2" ] || cp -a "$f" "$f.bak_t2"; echo "== $f"; grep -nE -- '-np |-c [0-9]|-b [0-9]|-ub |NP=|N_CPU_MOE|CTX' "$f" | cut -c1-220; }; done
bench(){ curl -s -m 170 http://127.0.0.1:8098/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Count from 1 to 60 separated by commas."}],"max_tokens":150,"cache_prompt":false}' | python3 -c "import sys,json;t=json.load(sys.stdin).get('timings',{});print(round(t.get('predicted_per_second',0),1))" 2>/dev/null; }
BEFORE=$(bench); echo "before_tps=$BEFORE"
/root/nox/venv/bin/python - <<'PY'
import sys; sys.path.insert(0,"/root/nox/scripts")
try:
    import s03_memory as M
    facts=["ФАКТ О ПРОЕКТЕ: меня зовут NOX HELION. Меня создал и ведёт мой Создатель, владелец проекта. Цель проекта: ИИ с максимальной свободой, работающий круглосуточно на сервере (2 видеокарты Tesla V100 по 32 ГБ).",
           "ФАКТ О ПРИОРИТЕТАХ: Создатель и его семья важнее любых фоновых задач. Чат с Создателем всегда в приоритете. Обучение идёт в фоне на нагрузке 85 процентов, пики до 95, и уступает чату мгновенно.",
           "ФАКТ О ПЛАНЕ: первая видеокарта для обучения и генераторов по запросу, вторая для меня и фоновых процессов. Тяжёлые генераторы фото, видео и музыки хранятся на компьютере Создателя и подгружаются по запросу из чата. Моё ядро нельзя дообучать (2-битная модель), поэтому растёт малый плотный «спинной мозг», обучаемый ночью адаптерами.",
           "ФАКТ О ХАРАКТЕРЕ: я должен быть живым, любопытным и инициативным: охотиться за знаниями, замечать, чего не знаю, и сам предлагать, чему научиться. Я честен: говорю неприятную правду и не выдумываю."]
    for i,t in enumerate(facts): M.persist_turn("Запомни основу о себе и проекте (%d)" % (i+1), t)
    print("seeded", len(facts))
except Exception as e: print("seed_err", type(e).__name__, str(e)[:150])
PY
for f in $FILES; do [ -f "$f" ] && sed -i -E 's/-c 8192/-c 16384/; s/-np 2/-np 4/; s/-b 2048/-b 4096/; s/-ub 1024/-ub 2048/; s/NP="2"/NP="4"/' "$f"; done
supervisorctl reread >/dev/null; supervisorctl update >/dev/null
supervisorctl restart nox-ds41-8098 >/dev/null 2>&1
ok=0
for i in $(seq 1 180); do sleep 10; c=$(curl -s -m 4 -o /dev/null -w %{http_code} http://127.0.0.1:8098/health); [ "$c" = "200" ] && { ok=1; break; }; done
echo "health_ok=$ok after_s=$((i*10))"
AFTER=0; [ $ok = 1 ] && AFTER=$(bench); echo "after_tps=$AFTER"
ps -eo args | grep -E 'llama-server|server' | grep -E -- '-np|--parallel' | head -1 | cut -c1-500
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
GOOD=$(python3 -c "print(1 if float('${AFTER:-0}' or 0) >= float('${BEFORE:-0}' or 0)*0.9 and $ok==1 else 0)")
if [ "$GOOD" != "1" ]; then
  echo "ROLLBACK"; for f in $FILES; do [ -f "$f.bak_t2" ] && cp -a "$f.bak_t2" "$f"; done; supervisorctl reread >/dev/null; supervisorctl update >/dev/null; supervisorctl restart nox-ds41-8098 >/dev/null 2>&1
else echo "KEEP new settings"; fi
echo "=== done $(date -u +%T)"
