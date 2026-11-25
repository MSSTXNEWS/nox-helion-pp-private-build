#!/usr/bin/env python3
import json, time, urllib.request, sys
B = 'http://127.0.0.1:8810'
def api(m, p, body=None, t=60):
    rq = urllib.request.Request(B + p, method=m, data=json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
    try: return json.loads(urllib.request.urlopen(rq, timeout=t).read())
    except Exception as e: return {'err': str(e)[:150]}
tid = api('POST', '/task', {'title': 'c4-palindrome', 'goal': 'Напиши python-функцию is_palindrome(s) и pytest-тест к ней', 'role': 'coder', 'source': 'chat'}).get('id'); print('TASK', tid, flush=True)
t0 = time.time(); print('SCAN', api('POST', '/worms/scan', t=240), round(time.time() - t0), 's', flush=True)
sc = api('GET', '/worms/cards', t=60); print('HUNT cards', [c['text'] for c in sc.get('hunt', [])][:3], flush=True); print('SELF cards', sc.get('self'), flush=True)
if sc.get('self'):
    cid = sc['self'][0]['id']; print('SELF apply', api('POST', '/worms/self/approve', {'id': cid, 'yes': True}), flush=True); print('SELF rollback', api('POST', '/worms/self/rollback/%d' % cid), flush=True)
t0 = time.time(); print('AGENDA make', api('POST', '/worms/agenda/make', t=200), round(time.time() - t0), 's', flush=True)
ag = api('GET', '/worms/agenda'); print('IDEAS', [(i['id'], i['title'][:60], i['status']) for i in ag.get('ideas', [])], flush=True)
if ag.get('ideas'): print('DEVELOP', api('POST', '/worms/develop', {'id': ag['ideas'][0]['id']}), flush=True)
t0 = time.time(); d = api('POST', '/consilium', {'question': 'Как лучше организовать уроки из ошибок для самообучения агентов?', 'deep': True, 'budget': 150}, t=240)
print('DEEP', round(time.time() - t0), 's', 'senior', d.get('senior'), 'waves', [(w['wave'], len(w['opinions'])) for w in d.get('waves', [])], 'err', d.get('errors'), 'final', str(d.get('final'))[:200].replace('\n', ' '), flush=True)
for _ in range(40):
    r = api('GET', '/task/%s/receipt' % tid)
    if 'task' in r: print('RECEIPT', json.dumps(r, ensure_ascii=False)[:900], flush=True); break
    time.sleep(10)
else: print('RECEIPT none yet', api('GET', '/task/%s/card' % tid), flush=True)
print('LIVE2 DONE', flush=True)
