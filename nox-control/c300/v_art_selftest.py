#!/usr/bin/env python3
"""Живой тест старших по рисованию -> реестр advisors_external.json (роли drawing_senior_gen / drawing_senior_critic)"""
import json, time, urllib.request, base64, os
G = 'http://127.0.0.1:8793/v1'; OUT = '/workspace/nox/state/advisors_external.json'
P = 'Котёнок сидит на подоконнике, за окном закат, тёплый свет, акварель'
def post(path, body, t=330):
    rq = urllib.request.Request(G + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try: return json.loads(urllib.request.urlopen(rq, timeout=t).read())
    except urllib.error.HTTPError as e: return {'error': e.read().decode()[:300]}
    except Exception as e: return {'error': str(e)[:200]}
res = []
def reg(entry):
    d = json.load(open(OUT)); d['advisors'] = [a for a in d['advisors'] if a['id'] != entry['id']] + [entry]
    d.setdefault('roles', {}); r = d['roles'].setdefault(entry['role'], [])
    if entry['id'] not in r: r.append(entry['id'])
    json.dump(d, open(OUT, 'w'), ensure_ascii=False, indent=1)
imgs = {}
GEN = [('pollinations/flux', 'Pollinations FLUX', '1 картинка / ~20 с на IP, анонимно, 768x768', 'фото-/иллюстративная генерация, быстро'),
       ('horde/', 'AI Horde (SDXL/Flux, анонимный ключ 0000000000)', 'очередь добровольцев, анонимный приоритет низкий; до ~5 мин; 576x576', 'разные SDXL-модели, медленно')]
for m, title, lim, st in GEN:
    t = time.time(); r = post('/images/generations', {'prompt': P, 'model': m, 'size': '768x768'}); ms = int((time.time() - t) * 1000)
    ok = 'data' in r; print('GEN', m, ms, 'ok' if ok else r, flush=True)
    if ok: imgs[m] = r['data'][0]['path']
    reg({'id': 'art_gen_' + m.replace('/', '_').strip('_'), 'role': 'drawing_senior_gen', 'provider': m.split('/')[0], 'model': m.split('/')[1] or 'auto', 'title': title, 'strengths': st, 'limits': lim,
         'status': 'ok' if ok else 'fail', 'latency_ms': ms, 'needs_key': False, 'call': 'POST :8793/v1/images/generations {prompt,model,size}', 'error': None if ok else str(r)[:200]})
CR = [('kilo/nvidia/nemotron-3.5-super-vl:free', 'NVIDIA Nemotron 3.5 Super VL (kilo free)'), ('kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free', 'NVIDIA Nemotron 3 Nano Omni (kilo free)')]
src = next(iter(imgs.values()), None)
for m, title in CR:
    if not src:
        reg({'id': 'art_critic_' + m.split('/', 1)[1].replace('/', '_').replace(':', '_'), 'role': 'drawing_senior_critic', 'provider': 'kilo', 'model': m.split('/', 1)[1], 'title': title, 'status': 'untested', 'strengths': 'vision', 'limits': '150 запросов/ч на IP (шлюз)', 'needs_key': False}); continue
    t = time.time(); r = post('/images/critique', {'image_path': src, 'prompt': P, 'model': m}); ms = int((time.time() - t) * 1000)
    ok = r.get('critique') is not None or bool(r.get('text')); sc = (r.get('critique') or {}).get('score')
    print('CRIT', m, ms, 'ok' if ok else r, 'score', sc, (r.get('text') or '')[:200].replace('\n', ' '), flush=True)
    reg({'id': 'art_critic_' + m.split('/', 1)[1].replace('/', '_').replace(':', '_'), 'role': 'drawing_senior_critic', 'provider': 'kilo', 'model': m.split('/', 1)[1], 'title': title, 'strengths': 'разбор композиции, анатомии, света, соответствия промпту; правки',
         'limits': '150 запросов/ч на IP (шлюз), 1 изображение за запрос', 'status': 'ok' if ok else 'fail', 'latency_ms': ms, 'needs_key': False, 'call': 'POST :8793/v1/images/critique {image_path|image_b64,prompt,model}', 'sample': (r.get('text') or str(r))[:300]})
for m, env, where in [('google/gemini-2.5-flash', 'GEMINI_API_KEY', 'aistudio.google.com/apikey'), ('groq/meta-llama/llama-4-scout-17b-16e-instruct', 'GROQ_API_KEY', 'console.groq.com/keys'), ('openrouter/qwen/qwen2.5-vl-32b-instruct:free', 'OPENROUTER_API_KEY', 'openrouter.ai/keys')]:
    reg({'id': 'art_critic_' + m.replace('/', '_').replace(':', '_'), 'role': 'drawing_senior_critic', 'provider': m.split('/')[0], 'model': m.split('/', 1)[1], 'title': m, 'strengths': 'vision', 'limits': 'бесплатный тариф', 'status': 'need_key', 'needs_key': True, 'key_env': env, 'key_where': where})
print('SELFTEST DONE', flush=True)
