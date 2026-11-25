#!/usr/bin/env python3
"""Прогон советников тестовым вопросом на русском, запись /workspace/nox/state/advisors_external.json"""
import json, time, urllib.request, os, sys
G = 'http://127.0.0.1:' + os.environ.get('ADV_PORT', '8793'); OUT = '/workspace/nox/state/advisors_external.json'
Q = 'Ответь одним предложением по-русски: какая столица Франции и сколько будет 17*3?'
STR = [('deepseek', 'рассуждения, код, математика'), ('qwen', 'многоязычность, код, длинный контекст'), ('llama', 'общие задачи, диалог'),
 ('mistral', 'быстрые ответы, европейские языки'), ('gemma', 'компактная, общие задачи'), ('gpt-oss', 'рассуждения, инструменты'),
 ('glm', 'агентные задачи, код'), ('minimax', 'длинный контекст, агенты'), ('nemotron', 'рассуждения, инструкции'), ('codestral', 'код'), ('phi', 'малая, логика')]
def strengths(m):
    for k, v in STR:
        if k in m.lower(): return v
    return 'общие задачи'
def get(u): return json.loads(urllib.request.urlopen(u, timeout=30).read())
def post(m):
    rq = urllib.request.Request(G + '/v1/chat/completions', data=json.dumps({'model': m, 'messages': [{'role': 'user', 'content': Q}], 'max_tokens': 200}).encode(), headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(rq, timeout=120).read())
LIM = {'llm7': '30 RPM анонимно (120 с токеном), по нашему лимиту 25/мин', 'pollinations': '1 запрос / 31 с на IP, анонимно'}
adv = []; ml = get(G + '/v1/models')['data']
todo = [m for m in ml if not m['needs_key']]
n7 = 0
for m in todo:
    p, name = m['id'].split('/', 1)
    if p == 'llm7':
        if n7 >= 14: continue
        n7 += 1
    t = time.time(); st = 'fail'; ans = ''
    try:
        r = post(m['id']); ans = r['choices'][0]['message']['content'][:160]; st = 'ok' if ans and ('Париж' in ans or '51' in ans) else 'weak'
    except Exception as e: ans = 'ERR ' + str(e)[:100]
    ms = int((time.time() - t) * 1000)
    adv.append({'id': 'ext_' + m['id'].replace('/', '_').replace(':', '_'), 'provider': p, 'model': name, 'strengths': strengths(name), 'status': 'ok' if st == 'weak' else st,
      'quality_ru': st, 'latency_ms': ms, 'needs_key': False, 'limits': LIM.get(p, ''), 'sample': ans})
    print(st, ms, m['id'], ans[:80].replace('\n', ' '), flush=True)
    json.dump({'updated': time.strftime('%Y-%m-%d %H:%M:%S'), 'gateway': G + '/v1', 'advisors': adv + []}, open(OUT, 'w'), ensure_ascii=False, indent=1)
# с ключом: заготовки
KEYED = [a for a in ml if a['needs_key']]
for m in KEYED:
    p, name = m['id'].split('/', 1)
    adv.append({'id': 'ext_' + m['id'].replace('/', '_').replace(':', '_'), 'provider': p, 'model': name, 'strengths': strengths(name), 'status': 'need_key' if not m['key_set'] else 'untested',
      'needs_key': True, 'key_env': {'openrouter': 'OPENROUTER_API_KEY', 'github': 'GITHUB_MODELS_TOKEN', 'groq': 'GROQ_API_KEY', 'cerebras': 'CEREBRAS_API_KEY', 'google': 'GEMINI_API_KEY', 'mistral': 'MISTRAL_API_KEY'}[p], 'limits': 'бесплатный тариф провайдера'})
json.dump({'updated': time.strftime('%Y-%m-%d %H:%M:%S'), 'gateway': G + '/v1', 'advisors': adv}, open(OUT, 'w'), ensure_ascii=False, indent=1)
print('DONE', sum(1 for a in adv if a['status'] == 'ok'), 'ok of', len(adv))
