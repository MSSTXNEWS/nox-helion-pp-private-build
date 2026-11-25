echo "C300: c_fetch7"
tail -c 3000 /workspace/nox/state/c_acc3.out | tail -25
python3 -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'));c=d.get('chat');print(json.dumps(c,ensure_ascii=False)[:2500])"
ps aux | grep -c "[q]a_audit"
