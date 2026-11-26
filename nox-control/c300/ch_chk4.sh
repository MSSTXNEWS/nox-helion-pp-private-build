echo "C300: ch_chk4"
N=/workspace/nox/state; tail -c 1800 $N/ch_audit1.log; echo; tail -c 600 $N/ch_crit.out | cut -c1-600; pgrep -af "qa_audit" | cut -c1-110 | head -3
python3 -I -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'));v=d.get('chat',{});print({k:v[k] for k in v if k!='items'})" 2>&1 | head -c 600
