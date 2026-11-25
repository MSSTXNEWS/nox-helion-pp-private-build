#!/usr/bin/env python3
"""Старшие советники по рисованию: генерация (pollinations flux, AI Horde) и арт-критика (vision). Подключается из gateway.py."""
import base64, json, os, re, time, urllib.parse, urllib.request, urllib.error, uuid, threading
ST = '/workspace/nox/state'; IMG = ST + '/advisor_images'; os.makedirs(IMG, exist_ok=True)
UA = {'User-Agent': 'nox-advisors/1.0', 'Client-Agent': 'nox-helion:1.0:owner'}
HORDE = 'https://aihorde.net/api/v2'
GEN_LOCK = {'pollinations': threading.Lock(), 'horde': threading.Lock()}
LAST = {}
GAP = {'pollinations': 20, 'horde': 5}
def _gap(p):
    w = LAST.get(p, 0) + GAP[p] - time.time()
    if w > 0: time.sleep(w)
    LAST[p] = time.time()
def _save(b, ext='png'):
    f = '%s/%s_%s.%s' % (IMG, time.strftime('%Y%m%d_%H%M%S'), uuid.uuid4().hex[:6], ext); open(f, 'wb').write(b); return f
def _ext(b): return 'webp' if b[:4] == b'RIFF' else 'jpg' if b[:2] == b'\xff\xd8' else 'png'
def gen_pollinations(prompt, model='flux', w=768, h=768, seed=None, timeout=120):
    q = {'model': model, 'width': w, 'height': h, 'nologo': 'true', 'private': 'true'}
    if seed is not None: q['seed'] = seed
    u = 'https://image.pollinations.ai/prompt/' + urllib.parse.quote(prompt) + '?' + urllib.parse.urlencode(q)
    with GEN_LOCK['pollinations']:
        _gap('pollinations')
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=timeout).read()
    if len(b) < 2000 or b[:1] in b'{<': raise ValueError('not image: ' + b[:120].decode('utf8', 'replace'))
    return b
def gen_horde(prompt, model=None, w=512, h=512, steps=25, timeout=280):
    key = os.environ.get('HORDE_API_KEY') or '0000000000'   # анонимный официальный ключ
    body = {'prompt': prompt, 'params': {'width': w, 'height': h, 'steps': steps, 'n': 1, 'sampler_name': 'k_euler_a', 'cfg_scale': 7}, 'nsfw': False, 'censor_nsfw': True, 'r2': True, 'shared': False}
    if model: body['models'] = [model]
    hd = dict(UA, apikey=key); hd['Content-Type'] = 'application/json'
    with GEN_LOCK['horde']:
        _gap('horde')
        r = json.loads(urllib.request.urlopen(urllib.request.Request(HORDE + '/generate/async', data=json.dumps(body).encode(), headers=hd), timeout=30).read())
        rid = r['id']; t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(6)
            c = json.loads(urllib.request.urlopen(urllib.request.Request(HORDE + '/generate/check/' + rid, headers=UA), timeout=30).read())
            if c.get('done'): break
            if c.get('faulted'): raise RuntimeError('horde faulted')
        else:
            try: urllib.request.urlopen(urllib.request.Request(HORDE + '/generate/status/' + rid, method='DELETE', headers=UA), timeout=15)
            except Exception: pass
            raise TimeoutError('horde queue timeout, waiting=%s' % c.get('wait_time'))
        s = json.loads(urllib.request.urlopen(urllib.request.Request(HORDE + '/generate/status/' + rid, headers=UA), timeout=30).read())
    g = s['generations'][0]; img = g['img']
    if img.startswith('http'): return urllib.request.urlopen(urllib.request.Request(img, headers=UA), timeout=60).read()
    return base64.b64decode(img)
def generate(prompt, model='auto', w=768, h=768, seed=None):
    """model: pollinations/flux | pollinations/<m> | horde[/<model>] | auto. -> (path, bytes, used, ms)"""
    t0 = time.time(); errs = []
    order = [model] if model != 'auto' else ['pollinations/flux', 'horde/']
    for m in order:
        p, _, name = m.partition('/')
        try:
            if p == 'pollinations': b = gen_pollinations(prompt, name or 'flux', w, h, seed)
            elif p == 'horde': b = gen_horde(prompt, name or None, min(w, 576), min(h, 576))
            else: raise ValueError('unknown provider')
            return _save(b, _ext(b)), b, m, int((time.time() - t0) * 1000)
        except Exception as e: errs.append('%s:%s' % (m, str(e)[:100]))
    raise RuntimeError('; '.join(errs))
CRIT_SYS = ('Ты старший арт-критик. Разбери рисунок по пунктам: 1) соответствие промпту, 2) композиция, 3) анатомия/пропорции/перспектива, 4) свет и цвет, 5) артефакты и дефекты. '
            'Дай оценку 0-10 по каждому пункту и итоговый балл, затем 3-5 конкретных правок для перерисовки (что изменить в промпте/картинке). Отвечай по-русски, коротко, в JSON: '
            '{"score":число,"prompt_match":число,"composition":число,"anatomy":число,"light_color":число,"issues":[...],"fixes":[...],"improved_prompt":"..."}')
def critique_msgs(img_bytes, prompt):
    """post_chat(model, messages) -> text. Изображение уходит наружу только вызывающий код разрешил."""
    mime = 'image/' + {'webp': 'webp', 'jpg': 'jpeg', 'png': 'png'}[_ext(img_bytes)]
    uri = 'data:%s;base64,%s' % (mime, base64.b64encode(img_bytes).decode())
    msgs = [{'role': 'system', 'content': CRIT_SYS}, {'role': 'user', 'content': [{'type': 'text', 'text': 'Исходный промпт: ' + prompt}, {'type': 'image_url', 'image_url': {'url': uri}}]}]
    return msgs
