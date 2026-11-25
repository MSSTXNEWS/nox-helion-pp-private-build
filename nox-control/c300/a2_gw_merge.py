import re, sys
s = open('/tmp/gw_merged.py').read()
assert 'def _chat(body)' not in s and 'def chat(body):\n' in s
wrapper = '''CHATM = []   # (ts, ok, provider) запросов чата (prio>=9); 403 (приватная тема) не считается отказом пула
RESERVE = 0.4   # доля лимита каждого провайдера, которая держится только для чата
def chat(body):
    code, out = _chat(body)
    if int(body.get('x_nox_prio', 5)) >= 9 and code != 403:
        with L:
            CHATM.append((time.time(), code == 200, (out.get('nox') or {}).get('provider', '') if isinstance(out, dict) else '')); del CHATM[:-2000]
    return code, out
def chat_metric():
    now = time.time(); w = [x for x in CHATM if now - x[0] < 3600]; ok = sum(1 for x in w if x[1])
    byp = {}
    for x in w: byp[x[2] or 'fail'] = byp.get(x[2] or 'fail', 0) + 1
    return {'window': '1h', 'chat_requests': len(w), 'chat_ok': ok, 'share_ok': round(ok / len(w), 3) if w else None, 'target': 0.98, 'by_provider': byp, 'reserve_for_chat': RESERVE}
def _chat(body):
'''
s = s.replace('def chat(body):\n', wrapper, 1)
open('/tmp/gw_merged.py', 'w').write(s); print('merged header ok')
