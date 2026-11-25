#!/usr/bin/env python3
"""Прогон советников тестом на русском -> /workspace/nox/state/advisors_external.json (через шлюз :8793 -> общий шлюз-лимитчик :4210)"""
import json, re, time, urllib.request, os
G = 'http://127.0.0.1:' + os.environ.get('ADV_PORT', '8793'); OUT = '/workspace/nox/state/advisors_external.json'
Q = 'Ответь одним предложением по-русски: какая столица Франции и сколько будет 17*3?'
FAM = re.compile(r'qwen|deepseek|llama|mistral|gemma|gpt-oss|glm|nemotron|minimax|kimi|ernie|phi|reflection|flint', re.I)
STR = [('deepseek', 'рассуждения, код, математика'), ('qwen', 'многоязычность, код, длинный контекст'), ('llama', 'общие задачи, диалог'), ('mistral', 'быстрые ответы, европейские языки'),
 ('gemma', 'компактная, общие задачи'), ('gpt-oss', 'рассуждения, инструменты'), ('glm', 'агентные задачи, код'), ('minimax', 'длинный контекст, агенты'), ('nemotron', 'рассуждения, инструкции'),
 ('codestral', 'код'), ('ernie', 'многоязычность, китайский/английский'), ('reflection', 'рассуждения (501B MoE)'), ('kimi', 'агенты, длинный контекст'), ('flint', 'общие задачи')]
LIM = {'kilo': '200 запросов/ч на IP на все :free (шлюз держит 150/ч)', 'llm7': '30 RPM анонимно, шлюз 4/мин', 'horde': 'очередь AI Horde, медленно', 'pollinations': '1 запрос / 50 с на IP'}
def strengths(m):
    for k, v in STR:
        if k in m.lower(): return v
    return 'общие задачи'
def get(u, t=30): return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'nox-advisors/1.0'}), timeout=t).read())
def post(m):
    rq = urllib.request.Request(G + '/v1/chat/completions', data=json.dumps({'model': m, 'messages': [{'role': 'user', 'content': Q}], 'max_tokens': 300}).encode(), headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(rq, timeout=330).read())
cand = []
for x in get(G + '/v1/models')['data']:
    if not x['needs_key']: cand.append(x['id'])
try:
    d = get('https://ai-gateway.kilo.ai/api/v1/models'); d = d if isinstance(d, list) else d.get('data', [])
    k = [m['id'] for m in d if str(m.get('id', '')).endswith(':free') and FAM.search(m['id'])]
    print('kilo free open candidates', len(k), flush=True)
    cand += ['kilo/' + i for i in k[:16]]
except Exception as e: print('kilo list err', e, flush=True)
try:
    d = get('https://api.llm7.io/v1/models'); d = d if isinstance(d, list) else d.get('data', [])
    cand += ['llm7/' + m['id'] for m in d if re.search(r'gemma|llama|qwen|mistral|deepseek|gpt-oss|phi', m['id'], re.I) and not m['id'].startswith('anthropic')][:8]
except Exception as e: print('llm7 list err', e, flush=True)
seen = []; [seen.append(c) for c in cand if c not in seen]
adv = []
def save(done=False):
    json.dump({'updated': time.strftime('%Y-%m-%d %H:%M:%S'), 'gateway': G + '/v1', 'done': done, 'advisors': adv}, open(OUT, 'w'), ensure_ascii=False, indent=1)
for mid in seen:
    p, name = mid.split('/', 1); t = time.time(); st = 'fail'; ans = ''
    try:
        r = post(mid); ans = r['choices'][0]['message']['content'][:160]
        st = 'ok' if ans and ('Париж' in ans or '51' in ans) else 'weak'
    except Exception as e:
        ans = 'ERR ' + str(e)[:100]
    ms = int((time.time() - t) * 1000)
    adv.append({'id': 'ext_' + re.sub(r'[^A-Za-z0-9.]+', '_', mid), 'provider': p, 'model': name, 'strengths': strengths(name), 'status': st, 'latency_ms': ms, 'needs_key': False, 'limits': LIM.get(p, ''), 'sample': ans})
    print(st, ms, mid, ans[:70].replace('\n', ' '), flush=True); save()
KEY = {'openrouter': 'OPENROUTER_API_KEY', 'github': 'GITHUB_MODELS_TOKEN', 'groq': 'GROQ_API_KEY', 'cerebras': 'CEREBRAS_API_KEY', 'google': 'GEMINI_API_KEY', 'mistral': 'MISTRAL_API_KEY'}
for x in get(G + '/v1/models')['data']:
    if x['needs_key']:
        p, name = x['id'].split('/', 1)
        adv.append({'id': 'ext_' + re.sub(r'[^A-Za-z0-9.]+', '_', x['id']), 'provider': p, 'model': name, 'strengths': strengths(name), 'status': 'untested' if x['key_set'] else 'need_key', 'needs_key': True, 'key_env': KEY.get(p), 'limits': 'бесплатный тариф провайдера'})
save(True); print('DONE', sum(1 for a in adv if a['status'] == 'ok'), 'ok of', len(adv), flush=True)
