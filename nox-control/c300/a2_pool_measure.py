"""замер пула: N разных запросов через :8793 (auto) 4 потоками; доли 200/429/502, время, кто ответил"""
import json, time, urllib.request, concurrent.futures as cf, sys, collections
N = int(sys.argv[1]) if len(sys.argv) > 1 else 24; tag = sys.argv[2] if len(sys.argv) > 2 else 'x'
def one(i):
    t = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8793/v1/chat/completions', data=json.dumps({'model': 'auto', 'messages': [{'role': 'user', 'content': f'[{tag}{i}] Назови {i + 3} разных фруктов через запятую.'}], 'max_tokens': 60, 'x_nox_prio': 5}).encode(), headers={'Content-Type': 'application/json'}), timeout=100)
        j = json.loads(r.read()); return 200, j.get('model') or '?', time.time() - t, (j.get('nox') or {}).get('label', '')
    except urllib.error.HTTPError as e: return e.code, '', time.time() - t, ''
    except Exception as e: return 0, type(e).__name__, time.time() - t, ''
t0 = time.time()
with cf.ThreadPoolExecutor(4) as ex: res = list(ex.map(one, range(N)))
dt = time.time() - t0; c = collections.Counter(r[0] for r in res); prov = collections.Counter(r[1].split('/')[0] for r in res if r[0] == 200)
print('MEASURE', tag, 'N', N, 'сек', round(dt), 'статусы', dict(c), 'ok%', round(100 * c[200] / N), '502%', round(100 * c[502] / N), '429%', round(100 * c[429] / N), 'провайдеры', dict(prov), 'экстраполяция/час ok', round(c[200] / dt * 3600), 'медиана с', round(sorted(r[2] for r in res)[N // 2], 1))
