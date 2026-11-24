cd /workspace/nox/web/site; touch qa/rework/chat.fixed qa/rework/cinema.fixed
python3 - <<'P'
import json
d=json.load(open('qa/audit.json'))['chat']
print(json.dumps(d,ensure_ascii=False)[:2500])
P
