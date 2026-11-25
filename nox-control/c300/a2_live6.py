import json, time, urllib.request, subprocess, os
B = 'http://127.0.0.1:8810'; A = '/workspace/nox/agents'; ST = '/workspace/nox/state'
def api(m, p, body=None, t=60):
    rq = urllib.request.Request(B + p, method=m, data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
    try: return json.loads(urllib.request.urlopen(rq, timeout=t).read())
    except Exception as e: return {'err': str(e)[:150]}
tid = api('POST', '/task', {'title': 'c6-markdown', 'goal': 'Напиши свой markdown-парсер на python с нуля: заголовки, списки, ссылки, жирный текст, функция md_to_html(text), и pytest-тест', 'role': 'coder', 'source': 'chat'}).get('id'); print('COACH task', tid, flush=True)
print('SCAN start', api('POST', '/worms/scan'), flush=True)
for env, name in ((None, 'EVAL20'), ('1', 'HOLDOUT10')):
    e = dict(os.environ); 
    if env: e['HOLDOUT'] = env
    out = subprocess.run(['python3', A + '/a2_eval_llm.py'], capture_output=True, text=True, env=e, timeout=400).stdout.strip().split('\n')
    print(name, [l for l in out if l.startswith('EVAL')], [l[:90] for l in out if l.startswith(('BAD', 'ERR'))], flush=True)
st = {}
for _ in range(30):
    st = api('GET', '/worms/scan/status'); 
    if not st.get('running'): break
    time.sleep(10)
print('SCAN status', json.dumps(st, ensure_ascii=False)[:500], flush=True)
sc = api('GET', '/worms/cards'); print('SELF cards', [c['text'][:110] for c in sc.get('self', [])], flush=True)
pl = ST + '/playbooks/_lessons.yaml'; before = open(pl).read() if os.path.exists(pl) else ''
if sc.get('self'):
    cid = sc['self'][0]['id']; print('SELF apply', api('POST', '/worms/self/approve', {'id': cid, 'yes': True}), flush=True)
    mid = open(pl).read(); print('SELF applied: lessons +', len(mid) - len(before), 'байт', flush=True)
    print('SELF rollback', api('POST', '/worms/self/rollback/%d' % cid), flush=True)
    print('SELF rolled back ok:', open(pl).read() == before, flush=True)
print('LEARNED', [x['text'][:80] for x in api('GET', '/worms/learned')][:4], flush=True)
t0 = time.time(); print('AGENDA force', api('POST', '/worms/agenda/make', {'force': True}, t=200), round(time.time() - t0), 's', flush=True)
ag = api('GET', '/worms/agenda'); print('AGENDA', ag.get('schedule'), ag.get('day_msk'), [(i['title'][:50], i['actions']) for i in ag.get('ideas', [])], flush=True)
t0 = time.time(); d = api('POST', '/consilium', {'question': 'Как лучше организовать уроки из ошибок для самообучения агентов?', 'deep': True, 'budget': 150}, t=240)
print('DEEP', round(time.time() - t0), 's', 'senior', d.get('senior'), 'waves', [(w['wave'], len(w['opinions'])) for w in d.get('waves', [])], 'err', d.get('errors'), 'cached', d.get('cached'), flush=True)
t0 = time.time()
while time.time() - t0 < 300:
    c = api('GET', '/task/%s' % tid)
    if c.get('status') in ('done', 'needs_owner', 'failed'): break
    time.sleep(10)
st = [(s['kind'], s['text'][:140]) for s in c.get('steps', []) if s['kind'] in ('coach', 'review', 'lesson')]
print('COACH task', c.get('status'), st[:6], flush=True)
print('LIVE6 DONE', flush=True)
