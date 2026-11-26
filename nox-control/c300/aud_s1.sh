echo "C300: aud_s1"
date -u; uptime; nproc; free -g | head -2; df -h /workspace / 2>/dev/null | tail -2
echo "== GPU"; nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw --format=csv,noheader 2>&1
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>&1 | while IFS=, read p m; do echo "$p $m $(ps -o comm=,etimes= -p $p 2>/dev/null) $(ps -o args= -p $p 2>/dev/null | grep -o -E '[a-z_0-9]+\.py|llama-server|--port [0-9]+' | tr '\n' ' ')"; done
echo "== top CPU"; ps -eo pid,pcpu,pmem,stat,etimes,comm --sort=-pcpu | head -22
echo "== stopped(T) procs"; ps -eo pid,stat,comm | awk '$2 ~ /^T/' | head -15
echo "== supervisor"; (supervisorctl status 2>/dev/null || /workspace/nox/venv/bin/supervisorctl status 2>/dev/null) | awk '{print $1,$2,$NF}' | head -60
echo "== ports"
for p in 18091 8091 8104 8105 8141 8144 8200 8300 8793 8810 8796 18217 18218 8510 8130 8400 8082 4000; do
  c=$(curl -s -o /dev/null -m 4 -w "%{http_code} %{time_total}" http://127.0.0.1:$p/health); echo "$p health=$c"; done
echo "== state flags"; ls -la --time-style=+%m-%dT%H:%M /workspace/nox/STOP /workspace/nox/state/OWNER_ACTIVE* /workspace/nox/state/orch/owner_active* /workspace/nox/state/PAUSE_MAIN /workspace/nox/agent/LIVE_TURN /workspace/nox/state/accel_tok_budget* 2>&1 | cut -c1-140
echo "== autotrain"; tail -25 /workspace/nox/agent/out/autotrain.log 2>/dev/null | cut -c1-230
L=$(ls -td /workspace/nox/agent/autotrain/rounds/r0*/ 2>/dev/null | head -1); echo "round $L"; ls -td /workspace/nox/agent/autotrain/rounds/r0*/ | head -14 | xargs -n1 basename | tr '\n' ' '; echo
grep -a -E "с/шаг|скорость|шаг [0-9]+, loss|VERDICT|вердикт|ACCEPT|REJECT|NO_GAIN|принят" ${L}train.log 2>/dev/null | tail -12 | cut -c1-220
echo "== verdicts history"
for d in $(ls -td /workspace/nox/agent/autotrain/rounds/r0*/ | head -16); do v=$(ls $d 2>/dev/null | grep -i -E "verdict|gate|result" | head -3 | tr '\n' ' '); echo "$(basename $d) $(stat -c %y $d | cut -c1-16) $v $(grep -h -o -E '"(decision|verdict|status|accepted|phase)": *"?[A-Za-z_0-9.]+' $d/*.json 2>/dev/null | head -4 | tr '\n' ' ')"; done
ls -la --time-style=+%m-%dT%H:%M /workspace/nox/distill_v2/ckpt_keep/ 2>/dev/null | grep -E "best|current|live|->" | cut -c30-200 | head
cat /workspace/nox/state/speed.json 2>/dev/null | head -c 700; echo
echo "== logs 6h errors"
cd /workspace/nox
find agent/out logs svc state/p3 ops /var/log/supervisor -maxdepth 2 -name "*.log" -mmin -360 -size +0 2>/dev/null | head -80 > /tmp/aud_logs
wc -l < /tmp/aud_logs
while read f; do n=$(tail -n 30000 "$f" | grep -a -c -i -E "traceback|error|exception|fatal|timeout|refused"); [ "$n" -gt 0 ] && echo "$n $f $(stat -c %s "$f")"; done < /tmp/aud_logs | sort -rn | head -25
echo "== top signatures"
while read f; do tail -n 30000 "$f" | grep -a -i -E "error|exception|fatal|timeout|refused" | sed -E 's/[A-Za-z0-9_\-]{24,}/<X>/g; s/(key|token|secret|password|auth)[^ ]*/<K>/Ig; s/[0-9]+/N/g' | cut -c1-110 | sed "s|^|$(basename $f): |"; done < /tmp/aud_logs | sort | uniq -c | sort -rn | head -30
echo "== big dirs"; du -sh /workspace/nox/* 2>/dev/null | sort -h | tail -12
echo "== cron count"; crontab -l 2>/dev/null | grep -v '^#' | grep -c .
echo END
