import json, time, urllib.request
B = 'http://127.0.0.1:8810'
def api(m, p, body=None, t=60):
    rq = urllib.request.Request(B + p, method=m, data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
    try: return json.loads(urllib.request.urlopen(rq, timeout=t).read())
    except Exception as e: return {'err': str(e)[:150]}
ids = [api('POST', '/task', {'title': 'c5-' + k, 'goal': g, 'role': r, 'source': 'chat'}).get('id') for k, g, r in [('palindrome', 'Напиши python-функцию is_palindrome(s) и pytest-тест к ней', 'coder'), ('readme2', 'Напиши README на 5 строк про карточки червей NOX', 'writer'), ('fizz', 'Напиши python-функцию fizzbuzz(n) и pytest-тест', 'coder')]]
print('TASKS', ids, flush=True)
for i in range(3):
    t = time.time(); print('LLM', i, api('POST', '/llm', {'prompt': 'Назови столицу Японии одним словом', 'max_tokens': 20}), round(time.time() - t, 1), flush=True)
t0 = time.time(); d = api('POST', '/consilium', {'question': 'Как лучше организовать уроки из ошибок для самообучения агентов?', 'deep': True, 'budget': 150}, t=240)
print('DEEP', round(time.time() - t0), 's', 'senior', d.get('senior'), 'waves', [(w['wave'], len(w['opinions'])) for w in d.get('waves', [])], 'err', d.get('errors'), 'final', str(d.get('final'))[:200].replace('\n', ' '), flush=True)
t0 = time.time()
while time.time() - t0 < 600:
    done = 0
    for tid in ids:
        r = api('GET', '/task/%s/receipt' % tid)
        if 'task' in r: done += 1; print('RECEIPT', tid, json.dumps({k: r[k] for k in ('title', 'accepted', 'seconds', 'fallbacks')}), [(a['path'], a['sha256'][:12], a['bytes']) for a in r['artifacts']], flush=True) if not r.get('_p') else None
    if done == len(ids): break
    time.sleep(15)
print('board', {k: len(v) for k, v in api('GET', '/board').items()}, 'metrics', api('GET', '/metrics').get('race'), flush=True)
print('LIVE4 DONE', flush=True)
