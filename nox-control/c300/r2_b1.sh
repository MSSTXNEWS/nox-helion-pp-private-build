cd /workspace/nox
pgrep -fa qa_audit | head -3
echo START
: > /tmp/r2_audit.log
setsid nohup bash -c 'for p in settings; do /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html >> /tmp/r2_audit.log 2>&1; echo DONE_$p >> /tmp/r2_audit.log; done' >/dev/null 2>&1 < /dev/null &
python3 - <<'P'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
print(len(a), sorted(a)[:60])
print(json.dumps(a['settings'],ensure_ascii=False)[:1500])
P
ls /workspace/nox/web/site/qa | head -30
grep -n "vendor_used\|handmade\|dead" /workspace/nox/qa_audit.py | head -20
