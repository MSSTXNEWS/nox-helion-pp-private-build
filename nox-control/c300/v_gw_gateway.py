#!/usr/bin/env python3
"""NOX advisors gateway: OpenAI-compatible /v1/chat/completions, model = provider/model. stdlib only. 127.0.0.1 only."""
import json, os, re, sys, time, threading, hashlib, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT = '/workspace/nox'; ST = ROOT + '/state'
ENV = ST + '/secrets/advisors.env'; CFG = ST + '/advisors_cfg.json'; USE = ST + '/advisors_usage.json'
REG = ST + '/advisors_external.json'; PORT = int(os.environ.get('ADV_PORT', '8793'))
DEFAULT_CFG = {"external_enabled": True, "allow_personal": False, "personal_terms": [], "cache_ttl": 3600,
  "timeout": 60, "retries": 1, "auto_chain": [], "max_tokens_cap": 2048}
# провайдер: base, ключ-ENV (None = без ключа), мин. интервал между запросами (с), RPM, дневная квота (оценка)
PROV = {
 'kilo': dict(base='http://127.0.0.1:4210/kilo/v1', env='KILO_API_KEY', gap=1.0, rpm=20, day=1500, keyless=True, timeout=90),
 'llm7': dict(base='http://127.0.0.1:4210/llm7/v1', env='LLM7_API_KEY', gap=2.5, rpm=4, day=600, keyless=True, timeout=90),
 'horde': dict(base='http://127.0.0.1:4210/horde/v1', env='HORDE_API_KEY', gap=8, rpm=3, day=300, keyless=True, timeout=300),
 'pollinations': dict(base='http://127.0.0.1:4210/pollinations/v1', env='POLLINATIONS_API_KEY', gap=50, rpm=1, day=1000, keyless=True, timeout=90),
 'openrouter': dict(base='https://openrouter.ai/api/v1', env='OPENROUTER_API_KEY', gap=3.5, rpm=18, day=50),
 'github': dict(base='https://models.github.ai/inference', env='GITHUB_MODELS_TOKEN', gap=5, rpm=10, day=150),
 'groq': dict(base='https://api.groq.com/openai/v1', env='GROQ_API_KEY', gap=2.2, rpm=28, day=1000),
 'cerebras': dict(base='https://api.cerebras.ai/v1', env='CEREBRAS_API_KEY', gap=2.2, rpm=28, day=1000),
 'google': dict(base='https://generativelanguage.googleapis.com/v1beta/openai', env='GEMINI_API_KEY', gap=4.5, rpm=12, day=250),
 'mistral': dict(base='https://api.mistral.ai/v1', env='MISTRAL_API_KEY', gap=2.5, rpm=20, day=500),
}
# статические модели для провайдеров с ключом (открытые), если /models недоступен
STATIC = {
 'openrouter': ['qwen/qwen3-235b-a22b:free', 'deepseek/deepseek-r1:free', 'meta-llama/llama-3.3-70b-instruct:free', 'google/gemma-3-27b-it:free', 'mistralai/mistral-small-3.2-24b-instruct:free', 'openai/gpt-oss-120b:free'],
 'github': ['deepseek/DeepSeek-R1', 'meta/Llama-3.3-70B-Instruct', 'mistral-ai/Mistral-Large-2411', 'microsoft/Phi-4'],
 'groq': ['llama-3.3-70b-versatile', 'openai/gpt-oss-120b', 'qwen/qwen3-32b', 'meta-llama/llama-4-scout-17b-16e-instruct'],
 'cerebras': ['llama-3.3-70b', 'qwen-3-32b', 'gpt-oss-120b'],
 'google': ['gemma-3-27b-it'],
 'mistral': ['open-mistral-nemo', 'mistral-small-latest'],
 'pollinations': ['openai'],
 'llm7': ['mistral-Nemo-Instruct-2407', 'codestral-latest'],
 'kilo': [], 'horde': [],
}
L = threading.Lock(); CACHE = {}; LAST = {}; WIN = {}; BAD = {}  # BAD: model-> until ts
def jload(p, d):
    try: return json.load(open(p))
    except Exception: return d
def cfg():
    c = dict(DEFAULT_CFG); c.update(jload(CFG, {})); return c
def keys():
    d = {}
    try:
        for ln in open(ENV):
            ln = ln.strip()
            if ln and not ln.startswith('#') and '=' in ln:
                k, v = ln.split('=', 1); v = v.strip().strip('"\'')
                if v: d[k.strip()] = v
    except Exception: pass
    return d
def key_of(p):
    pr = PROV[p]; k = keys().get(pr['env'])
    return k or pr.get('anon')
def avail(p): return bool(key_of(p)) if not PROV[p].get('keyless') else True
# ---- приватность
PAT = [(re.compile(r'(?i)\b(sk|gsk|csk|pk|rk)[-_][A-Za-z0-9_\-]{16,}'), '[KEY]'),
 (re.compile(r'\b(ghp|gho|ghu|ghs|ghr|github_pat|hf|xox[abp])[_-][A-Za-z0-9_\-]{16,}'), '[TOKEN]'),
 (re.compile(r'\bAIza[0-9A-Za-z_\-]{30,}'), '[KEY]'), (re.compile(r'(?i)bearer\s+[A-Za-z0-9._\-]{16,}'), 'Bearer [TOKEN]'),
 (re.compile(r'(?i)\b(api[_-]?key|token|secret|password|passwd|пароль|ключ)\s*[:=]\s*\S{6,}'), r'\1=[SECRET]'),
 (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.S), '[PRIVATE_KEY]'),
 (re.compile(r'(?<![\w/])(?:/(?:workspace|home|root|etc|var|opt|mnt|srv|usr|tmp)/[^\s"\'`<>)]*)'), '[PATH]'),
 (re.compile(r'\b[A-Za-z]:\\[^\s"\']+'), '[PATH]'),
 (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '[EMAIL]'),
 (re.compile(r'\b\d{1,3}(?:\.\d{1,3}){3}\b'), '[IP]'),
 (re.compile(r'\b[A-Fa-f0-9]{32,}\b'), '[HEX]'), (re.compile(r'\b[A-Za-z0-9+/_\-]{40,}={0,2}'), '[BLOB]')]
PERS = [(re.compile(r'(?<!\d)(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)'), '[PHONE]'),
 (re.compile(r'(?i)алуштинск\w*|ленинск\w+\s+районн\w+\s+суд\w*'), '[ADDR]'),
 (re.compile(r'\b\d{4}\s?\d{6}\b'), '[DOC]')]
def sanitize(t, c):
    n = 0
    for rx, rep in PAT + ([] if c.get('allow_personal') else PERS):
        t, k = rx.subn(rep, t); n += k
    if not c.get('allow_personal'):
        for w in c.get('personal_terms', []):
            if w:
                t, k = re.subn(re.escape(w), '[PERSON]', t, flags=re.I); n += k
    return t, n
# ---- лимиты/квоты
def usage():
    return jload(USE, {})
def count(p, ok):
    with L:
        u = usage(); day = time.strftime('%Y-%m-%d'); r = u.setdefault(p, {})
        if r.get('day') != day: r.clear(); r['day'] = day
        r['n'] = r.get('n', 0) + 1; r['ok'] = r.get('ok', 0) + (1 if ok else 0)
        try: json.dump(u, open(USE, 'w'))
        except Exception: pass
def day_left(p):
    r = usage().get(p, {}); used = r.get('n', 0) if r.get('day') == time.strftime('%Y-%m-%d') else 0
    return PROV[p]['day'] - used
def wait_slot(p, maxwait):
    pr = PROV[p]; t0 = time.time()
    while True:
        with L:
            now = time.time(); w = WIN.setdefault(p, [])
            w[:] = [x for x in w if now - x < 60]
            need = max(LAST.get(p, 0) + pr['gap'] - now, 0)
            if len(w) >= pr['rpm']: need = max(need, 60 - (now - w[0]))
            if need <= 0:
                LAST[p] = now; w.append(now); return True
        if time.time() - t0 + need > maxwait: return False
        time.sleep(min(need, 1.0))
# ---- вызов
def http(url, body, key, timeout):
    h = {'Content-Type': 'application/json', 'User-Agent': 'nox-advisors/1.0'}
    if key: h['Authorization'] = 'Bearer ' + key
    rq = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h)
    with urllib.request.urlopen(rq, timeout=timeout) as r: return json.loads(r.read().decode())
def call(p, model, body, timeout):
    pr = PROV[p]; url = pr['base'] + ('' if pr.get('full') else '/chat/completions')
    b = dict(body); b['model'] = model; b['stream'] = False
    return http(url, b, None if pr.get('keyless') else key_of(p), max(timeout, pr.get('timeout', 0)))
def models_of(p):
    out = [a['model'] for a in jload(REG, {}).get('advisors', []) if a.get('provider') == p]
    try:
        for m in jload('/workspace/nox/router/router/catalog.json', {}).get('models', []):
            if m.get('no_key') and m.get('enabled') and m.get('advisor') and ('/%s/' % p) in (m.get('api_base') or ''):
                out.append(m['litellm_model'].split('/', 1)[1] if m.get('litellm_model', '').startswith('openai/') else m.get('litellm_model'))
    except Exception: pass
    seen = []
    for x in out + STATIC.get(p, []):
        if x and x not in seen: seen.append(x)
    return seen

def clean_text(r):
    try:
        m = r['choices'][0]['message']; t = m.get('content') or ''
        t = re.sub(r'(?s)<think>.*?</think>', '', t).strip()
        return t
    except Exception: return ''
def chat(body):
    c = cfg(); t0 = time.time()
    if not c['external_enabled']: return 403, {'error': 'external advisors disabled in advisors_cfg.json'}
    msgs = body.get('messages') or []
    nred = 0; sm = []
    for m in msgs:
        tx = m.get('content')
        if isinstance(tx, list): tx = ' '.join(x.get('text', '') for x in tx if isinstance(x, dict))
        tx, k = sanitize(str(tx or ''), c); nred += k; sm.append({'role': m.get('role', 'user'), 'content': tx})
    nb = {'messages': sm, 'max_tokens': min(int(body.get('max_tokens') or 1024), c['max_tokens_cap'])}
    if 'temperature' in body: nb['temperature'] = body['temperature']
    want = body.get('model', 'auto')
    chain = []
    if '/' in want and want.split('/', 1)[0] in PROV and want.split('/', 1)[1] not in ('auto', ''):
        chain = [tuple(want.split('/', 1))]
    else:
        reg = jload(REG, {}).get('advisors', [])
        pref = want.split('/', 1)[0] if want.split('/', 1)[0] in PROV else None
        cand = [(a['provider'], a['model']) for a in reg if a.get('status') in ('ok','untested','need_key') and avail(a['provider']) and (not pref or a['provider'] == pref)]
        chain = cand or [tuple(x.split('/', 1)) for x in c['auto_chain']]
    ck = hashlib.sha256(json.dumps([want, nb], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with L:
        h = CACHE.get(ck)
    if h and time.time() - h[0] < c['cache_ttl']:
        r = dict(h[1]); r['nox'] = dict(r.get('nox', {}), cached=True); return 200, r
    tried = []
    for p, m in chain:
        if p not in PROV or not avail(p) or BAD.get(p + '/' + m, 0) > time.time() or day_left(p) <= 0: continue
        for att in range(1 + int(c['retries'])):
            if not wait_slot(p, 40): tried.append(p + '/' + m + ':busy'); break
            try:
                r = call(p, m, nb, c['timeout'])
                tx = clean_text(r)
                if not tx: raise ValueError('empty')
                count(p, True)
                out = {'id': 'nox-' + ck[:12], 'object': 'chat.completion', 'created': int(time.time()), 'model': p + '/' + m,
                       'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': tx}, 'finish_reason': 'stop'}],
                       'usage': r.get('usage', {}), 'nox': {'provider': p, 'redacted': nred, 'ms': int((time.time() - t0) * 1000), 'tried': tried, 'cached': False}}
                with L: CACHE[ck] = (time.time(), out)
                return 200, out
            except urllib.error.HTTPError as e:
                count(p, False); tried.append('%s/%s:%d' % (p, m, e.code))
                if e.code in (401, 403, 404): BAD[p + '/' + m] = time.time() + 600; break
                if e.code in (402, 429): BAD[p + '/' + m] = time.time() + 60; break
            except Exception as e:
                count(p, False); tried.append('%s/%s:%s' % (p, m, type(e).__name__))
                BAD[p + '/' + m] = time.time() + 120 if att else BAD.get(p + '/' + m, 0)
    return 502, {'error': 'all advisors failed', 'tried': tried}
def listing():
    reg = {(a['provider'], a['model']): a for a in jload(REG, {}).get('advisors', [])}; data = []
    for p in PROV:
        for m in models_of(p):
            a = reg.get((p, m), {})
            data.append({'id': p + '/' + m, 'object': 'model', 'owned_by': p, 'available': avail(p) and day_left(p) > 0,
                         'needs_key': not PROV[p].get('keyless'), 'key_set': bool(keys().get(PROV[p]['env'])), 'status': a.get('status', 'untested'), 'latency_ms': a.get('latency_ms')})
    return {'object': 'list', 'data': data, 'usage': usage()}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith('/v1/models'): return self.send(200, listing())
        if self.path.startswith('/health'): return self.send(200, {'ok': True, 'port': PORT, 'cfg': {k: v for k, v in cfg().items() if k != 'personal_terms'}})
        self.send(404, {'error': 'not found'})
    def do_POST(self):
        if not self.path.startswith('/v1/chat/completions'): return self.send(404, {'error': 'not found'})
        try:
            n = int(self.headers.get('Content-Length', 0)); body = json.loads(self.rfile.read(n) or b'{}')
        except Exception: return self.send(400, {'error': 'bad json'})
        code, out = chat(body); self.send(code, out)
if __name__ == '__main__':
    os.makedirs(ST + '/secrets', exist_ok=True)
    if not os.path.exists(CFG): json.dump(DEFAULT_CFG, open(CFG, 'w'), ensure_ascii=False, indent=2)
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
