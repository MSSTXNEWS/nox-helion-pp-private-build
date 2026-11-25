import json, time, urllib.request, concurrent.futures as cf, sys
def get(u, t=15, h=None):
    return urllib.request.urlopen(urllib.request.Request(u, headers=h or {'User-Agent': 'nox-advisors/1.0'}), timeout=t).read().decode()
def post(u, body, t=40):
    try:
        r = urllib.request.urlopen(urllib.request.Request(u, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'User-Agent': 'nox-advisors/1.0'}), timeout=t)
        return r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:120]
    except Exception as e: return 0, type(e).__name__
print('== local ports')
for p in (8104, 8141, 8142, 8151, 8152, 8811, 8812):
    try:
        m = json.loads(get('http://127.0.0.1:%d/v1/models' % p, 5))['data'][0]['id']; t = time.time(); s, b = post('http://127.0.0.1:%d/v1/chat/completions' % p, {'model': m, 'messages': [{'role': 'user', 'content': 'скажи ок'}], 'max_tokens': 5}, 25)
        print(p, m, s, round(time.time() - t, 1), 's', b[:60].replace('\n', ' '))
    except Exception as e: print(p, 'нет', type(e).__name__)
print('== pollinations models')
try: ms = json.loads(get('https://text.pollinations.ai/models', 15)); print([m.get('name') for m in ms][:20])
except Exception as e: print('ERR', e)
print('== llm7 models + test')
try:
    ms = json.loads(get('https://api.llm7.io/v1/models', 15)); ids = [m['id'] for m in (ms if isinstance(ms, list) else ms.get('data', []))]; print(len(ids), ids[:25])
    for m in ids[:40]:
        if any(x in m.lower() for x in ('gpt-oss', 'qwen', 'llama', 'deepseek', 'mistral', 'gemma')):
            s, b = post('https://api.llm7.io/v1/chat/completions', {'model': m, 'messages': [{'role': 'user', 'content': 'скажи ок'}], 'max_tokens': 8}, 30); print('  llm7', m, s, b[:70].replace('\n', ' '))
except Exception as e: print('ERR', e)
print('== kilo free models')
try:
    d = json.loads(get('https://ai-gateway.kilo.ai/api/v1/models', 20)); d = d if isinstance(d, list) else d.get('data', []); fr = [m['id'] for m in d if str(m['id']).endswith(':free')]; print(len(fr), fr[:30])
except Exception as e: print('ERR', e)
print('== HF Spaces gradio')
try:
    sp = json.loads(get('https://huggingface.co/api/spaces?filter=gradio&search=qwen+chat&sort=likes&limit=8', 20)); print([(s['id'], s.get('sdk'), s.get('runtime', {}).get('stage') if isinstance(s.get('runtime'), dict) else None) for s in sp])
except Exception as e: print('ERR', e)
try:
    import gradio_client; print('gradio_client', gradio_client.__version__)
except Exception as e: print('gradio_client нет', e)
