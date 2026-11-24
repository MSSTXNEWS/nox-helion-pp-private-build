RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/qa_audit.py" -o /workspace/nox/qa_audit.py
cat /workspace/nox/web/site/qa/history.log 2>/dev/null | tail -3
cat > /workspace/nox/qa_audit_loop.sh <<'L'
#!/bin/bash
# аудит по ТЗ раз в час + сразу после отметки «исправлено» (файл qa/rework/*.fixed)
while true; do
  for f in /workspace/nox/web/site/qa/rework/*.fixed; do [ -e "$f" ] || continue; k=$(basename "$f" .fixed); rm -f "$f"; flock /tmp/qaa.lock nice -n 15 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py "$k.html" >> /workspace/nox/agent/out/qa_audit.log 2>&1; done
  if [ $(( $(date +%s) - $(stat -c %Y /workspace/nox/web/site/qa/audit.json 2>/dev/null || echo 0) )) -gt 3600 ]; then flock -n /tmp/qaa.lock nice -n 15 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py >> /workspace/nox/agent/out/qa_audit.log 2>&1; fi
  sleep 60
done
L
chmod +x /workspace/nox/qa_audit_loop.sh
grep -q qa_audit_loop /root/onstart.sh || echo 'nohup /workspace/nox/qa_audit_loop.sh >/dev/null 2>&1 &' >> /root/onstart.sh
pgrep -f qa_audit_loop.sh >/dev/null || nohup setsid /workspace/nox/qa_audit_loop.sh >/dev/null 2>&1 < /dev/null &
timeout 250 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py chat.html; tail -c 1500 /workspace/nox/web/site/qa/audit.json
