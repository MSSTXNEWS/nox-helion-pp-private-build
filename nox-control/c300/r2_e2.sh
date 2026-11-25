grep -n "^settings\|^DONE\|^photo\|^atlas\|^index\|^news\|^chat\|^finance" /tmp/r2_audit.log | cut -c1-700
python3 - <<'P'
import json
for k in ('settings',):
    d=json.load(open('/workspace/nox/web/site/qa/rework/%s.json'%k)); print(json.dumps(d,ensure_ascii=False)[:900])
P
pgrep -fa "qa_audit.py" | cut -c1-100
