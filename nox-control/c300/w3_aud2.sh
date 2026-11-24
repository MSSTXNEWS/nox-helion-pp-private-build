cd /workspace/nox/web/site; touch qa/rework/news.fixed
python3 - <<'P'
import json
d=json.load(open('qa/audit.json'))
for k,v in d.items():
    print(k,v.get('ts'),v.get('status'),'wow',v.get('wow'),'fails',len(v.get('fails',[])))
for k in ('studio','photo','tools'):
    try: r=json.load(open(f'qa/rework/{k}.json')); print('==',k,r.get('cycle'),json.dumps(r.get('fails'),ensure_ascii=False)[:900],json.dumps(r.get('fix'),ensure_ascii=False)[:700])
    except Exception as e: print(k,e)
P
ls qa/rework; ls qa | head -20
python3 - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/report.json'))
print(json.dumps(r,ensure_ascii=False)[:1500])
P
