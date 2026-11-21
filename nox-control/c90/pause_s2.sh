#!/bin/bash
# c90: ПАУЗА всех процессов S2 по решению владельца. SIGSTOP (не kill): память/RAM-модель сохраняются, возобновление: bash /root/nox/scripts/resume_s2.sh
# Не трогаем: sshd, supervisord, nox-cmd-agent (канал управления).
mkdir -p /root/nox/scripts /root/nox/state
KEEP='nox-cmd-agent'
LIST=/root/nox/state/paused_pids.txt; : > $LIST
supervisorctl status 2>/dev/null | awk '$2=="RUNNING"{print $1}' | grep -vE "^($KEEP)$" | while read p; do
  pid=$(supervisorctl pid $p 2>/dev/null | tr -dc 0-9)
  [ -n "$pid" ] && [ "$pid" -gt 1 ] || continue
  # группа процесса целиком (дети тоже), чтобы остановить воркеры
  pg=$(ps -o pgid= -p $pid | tr -d ' ')
  kill -STOP -- -$pg 2>/dev/null || kill -STOP $pid
  echo "$p $pid $pg" >> $LIST
done
cat > /root/nox/scripts/resume_s2.sh <<'R'
#!/bin/bash
while read p pid pg; do kill -CONT -- -$pg 2>/dev/null || kill -CONT $pid 2>/dev/null; echo "resumed $p"; done < /root/nox/state/paused_pids.txt
R
chmod +x /root/nox/scripts/resume_s2.sh
echo "== paused: $(wc -l < $LIST) процессных групп"; awk '{print $1}' $LIST | tr '\n' ' ' | cut -c1-900; echo
sleep 3; echo "== GPU"; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
echo "== проверка: stopped(T) процессов:"; ps -eo stat,comm | awk '$1 ~ /^T/' | sort | uniq -c | sort -rn | head -6
