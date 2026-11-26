#!/usr/bin/env python3
"""NOX api_bridge: тонкий мост с реальными источниками для /api/* панелей. Нет данных -> 200 + hold:true."""
import asyncio, json, os, sys, time, socket
from aiohttp import web, ClientSession, ClientTimeout
N = '/workspace/nox'
PORT = int(os.environ.get('BRIDGE_PORT', '8796'))
BOARD = 'http://127.0.0.1:8810'
SETTINGS = N + '/state/ui_settings.json'
SERVICES = {'web': 8091, 'board': 8810, 'models_swap': 8200, 'litellm': 4000, 'vision': 8104, 'gateway': 8097, 'search': 8097}

def rj(path):
    try:
        with open(path, encoding='utf-8') as f: return json.load(f)
    except Exception: return None

def hold(reason, **kw):
    d = {'ok': True, 'hold': True, 'status': 'HOLD', 'hold_reason': reason, 'ts': int(time.time())}
    d.update(kw); return d

async def board(path):
    try:
        async with ClientSession(timeout=ClientTimeout(total=4)) as s:
            async with s.get(BOARD + path) as r:
                return await r.json(content_type=None) if r.status == 200 else None
    except Exception:
        return None

def last_round():
    r = rj(N + '/agent/out/round_last.json') or {}
    best = None
    try:
        with open(N + '/agent/out/round_best_history.jsonl', 'rb') as f:
            f.seek(0, 2); n = f.tell(); f.seek(max(0, n - 4000)); lines = f.read().decode('utf-8', 'ignore').strip().splitlines()
        for l in reversed(lines):
            try: best = json.loads(l); break
            except Exception: continue
    except Exception: pass
    return r, best

SLOT_PORTS = {'8104': 'vision', '8811': 'llama-8811', '8812': 'llama-8812', '8151': 'llama-8151', '8152': 'llama-8152'}

async def slots_state():
    """Реальный счётчик: llama-server /slots, is_processing. None если ни один не ответил."""
    async def one(sess, port):
        try:
            async with sess.get('http://127.0.0.1:%s/slots' % port) as r:
                if r.status != 200: return None
                j = await r.json(content_type=None)
                return sum(1 for x in j if x.get('is_processing')) if isinstance(j, list) else None
        except Exception: return None
    async with ClientSession(timeout=ClientTimeout(total=2)) as sess:
        res = await asyncio.gather(*[one(sess, p) for p in SLOT_PORTS])
    ok = {SLOT_PORTS[p]: c for p, c in zip(SLOT_PORTS, res) if c is not None}
    if not ok: return None
    return {'active_generations': sum(ok.values()), 'per_server': ok, 'servers_observed': len(ok), 'sampled_at': time.time(), 'source': 'llama-server /slots is_processing'}

async def training(request):
    v = rj(N + '/state/p3/train_verdict.json'); r, b = last_round()
    if not v and not r: return web.json_response(hold('нет train_verdict.json и round_last.json'))
    d = {'ok': True, 'ts': int(time.time()), 'source': 'state/p3/train_verdict.json + agent/out/round_last.json'}
    if v: d.update({'verdict': v.get('verdict'), 'status': v.get('verdict'), 'accepted': v.get('accepted'), 'last_gates': v.get('last_gates'), 'note': v.get('note'), 'verdict_ts': v.get('t')})
    if r: d.update({'round': r.get('round'), 'rows_total': r.get('rows_total'), 'new_rows': r.get('new_rows'), 'total_min': r.get('total_min')})
    if b: d.update({'best': b.get('best'), 'step': b.get('step'), 'best_ts': b.get('t')})
    try:
        import glob, re, datetime
        ck = sorted(glob.glob(N + '/distill_v2/ckpt_keep/*'))
        d['checkpoint_count'] = len(ck)
        bd = (v or {}).get('best_dir') or ''
        m = re.search(r'step_(\d+)', bd)
        if m: d['checkpoints'] = [{'step': int(m.group(1)), 'name': os.path.basename(bd)}]
        if v and v.get('t'):
            t0 = datetime.datetime.strptime(v['t'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc).timestamp()
            d['receipt_age_seconds'] = max(0, int(time.time() - t0))
    except Exception: pass
    if v: d['phase'] = v.get('verdict')
    if r: d['cycle'] = r.get('round')
    if b and b.get('step') is not None: d['step'] = b.get('step')
    sl = await slots_state()
    if sl: d['generation_slots'] = sl
    return web.json_response(d)

async def activity(request):
    b = await board('/board'); h = await board('/health')
    if b is None: return web.json_response(hold('панель задач :8810 недоступна'))
    cols = {k: (v if isinstance(v, list) else []) for k, v in b.items()}
    def slim(t): return {k: t.get(k) for k in ('id', 'title', 'column', 'stage', 'doing', 'pct', 'blocker', 'idle_sec')}
    items = [slim(t) for c in ('Нужен ты', 'В работе', 'Очередь') for t in cols.get(c, [])]
    done = [slim(t) for t in cols.get('Готово', [])[:5]]
    d = {'ok': True, 'ts': int(time.time()), 'source': ':8810 /board', 'counts': {k: len(v) for k, v in cols.items()},
         'active': len(cols.get('В работе', [])) > 0, 'items': items, 'recent_done': done}
    if h:
        d.update({'running': h.get('running'), 'queued': h.get('queued'), 'inflight': h.get('inflight')})
    sl = await slots_state()
    if sl:
        d.update({'status': 'OBSERVED_NATIVE_OWNER', 'active_generations': sl['active_generations'], 'sampled_at': sl['sampled_at'], 'phases': {}, 'generation_source': sl['source'], 'per_server': sl['per_server']})
    else:
        d.update({'status': 'HOLD', 'hold': True, 'hold_reason': 'счётчик генераций недоступен (/slots не отвечает)'})
    if not items: d['note'] = 'Активных задач нет'
    return web.json_response(d)

async def notifications(request):
    w = await board('/worms/learned'); ag = rj(N + '/state/agenda_check.json')
    if w is None and not ag: return web.json_response(hold('нет данных :8810 /worms/learned и agenda_check.json'))
    items = []
    if isinstance(w, list):
        for x in w[:30]:
            items.append({'ts': x.get('ts'), 'text': x.get('text'), 'kind': 'learned'})
    events = [{'id': int(x['ts']), 'message': x['text'], 'ts': x['ts']} for x in items if isinstance(x.get('ts'), (int, float)) and x.get('text')]
    events.sort(key=lambda e: -e['id'])
    d = {'ok': True, 'ts': int(time.time()), 'source': ':8810 /worms/learned + state/agenda_check.json', 'events': events, 'items': items, 'notifications': items, 'unread': 0}
    if ag: d['agenda'] = ag
    if not items: d['note'] = 'Новых уведомлений нет'
    return web.json_response(d)

async def settings(request):
    if request.method in ('POST', 'PUT', 'PATCH'):
        try:
            if request.content_length and request.content_length > 65536: return web.json_response({'ok': False, 'error': 'too large'}, status=413)
            body = await request.json()
            if not isinstance(body, dict): raise ValueError('object expected')
            cur = rj(SETTINGS) or {}
            if not isinstance(cur, dict): cur = {}
            cur.update(body.get('settings', body) if isinstance(body.get('settings', body), dict) else body)
            tmp = SETTINGS + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f: json.dump(cur, f, ensure_ascii=False)
            os.replace(tmp, SETTINGS)
            return web.json_response({'ok': True, 'settings': cur, **cur})
        except Exception as e:
            return web.json_response({'ok': False, 'error': str(e)[:120]}, status=400)
    cur = rj(SETTINGS)
    if cur is None: return web.json_response(hold('настройки ещё не сохранялись (state/ui_settings.json нет)', settings={}, stored=False))
    return web.json_response({'ok': True, 'stored': True, 'settings': cur, 'ts': int(time.time()), **cur})

def up(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.6): return True
    except Exception: return False

async def status(request):
    loop = asyncio.get_running_loop()
    res = await asyncio.gather(*[loop.run_in_executor(None, up, p) for p in SERVICES.values()])
    sv = {k: {'port': p, 'up': u} for (k, p), u in zip(SERVICES.items(), res)}
    n = sum(1 for v in sv.values() if v['up'])
    out = {'ok': True, 'ts': int(time.time()), 'source': 'tcp health сервисов', 'services': sv, 'up': n, 'total': len(sv), 'status': 'ok' if n == len(sv) else 'degraded'}
    try:
        async with ClientSession(timeout=ClientTimeout(total=4)) as sess:
            async with sess.get('http://127.0.0.1:8091/api/nox/status') as r:
                if r.status == 200:
                    up_d = await r.json(content_type=None)
                    if isinstance(up_d, dict):
                        up_d.update({'services': sv, 'services_up': n, 'services_total': len(sv)}); out = up_d
    except Exception: pass
    return web.json_response(out)


async def sci_arxiv(request):
    """Поиск arXiv (у arXiv нет CORS): мост ходит сам. Нет ответа -> hold."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote
    q = request.query.get('q', '').strip()[:200]
    if not q: return web.json_response(hold('пустой запрос', items=[]))
    try:
        async with ClientSession(timeout=ClientTimeout(total=12)) as sess:
            async with sess.get('http://export.arxiv.org/api/query?search_query=all:' + quote(q) + '&max_results=8') as r:
                if r.status != 200: return web.json_response(hold('arXiv ответил %s' % r.status, items=[]))
                xml = await r.text()
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        items = []
        for e in ET.fromstring(xml).findall('a:entry', ns):
            g = lambda t: (e.findtext('a:' + t, '', ns) or '').strip()
            items.append({'title': ' '.join(g('title').split()), 'url': g('id'), 'year': g('published')[:4], 'authors': [(a.findtext('a:name', '', ns) or '').strip() for a in e.findall('a:author', ns)][:6], 'venue': 'arXiv', 'summary': ' '.join(g('summary').split())[:300]})
        return web.json_response({'ok': True, 'source': 'arXiv API', 'items': items, 'ts': int(time.time())})
    except Exception as ex:
        return web.json_response(hold('arXiv недоступен: %s' % str(ex)[:80], items=[]))

def state_json(rel, what):
    path = N + '/state/' + rel
    d = rj(path)
    if d is None: return hold('%s: нет данных (state/%s отсутствует)' % (what, rel))
    try: mt = int(os.path.getmtime(path))
    except Exception: mt = 0
    return {'ok': True, 'ts': int(time.time()), 'mtime': mt, 'source': 'state/' + rel, 'data': d}

async def self_now(request):
    return web.json_response(state_json('core/self_now.json', 'Я сейчас'))

async def briefs(request):
    return web.json_response({'ok': True, 'ts': int(time.time()), 'morning': state_json('mind/morning_brief_v5.json', 'утренний бриф'), 'evening': state_json('mind/evening_brief_v5.json', 'вечерний бриф')})

async def sci_semantic(request):
    q = request.query.get('q', '').strip()[:200]
    if not q: return web.json_response({'data': []})
    try:
        async with ClientSession(timeout=ClientTimeout(total=15)) as c:
            async with c.get('https://api.semanticscholar.org/graph/v1/paper/search', params={'limit': '8', 'fields': 'title,year,authors,externalIds,url,venue', 'query': q}) as r:
                if r.status != 200: return web.json_response(hold('Semantic Scholar: HTTP %s' % r.status, data=[]))
                return web.json_response(await r.json())
    except Exception as ex:
        return web.json_response(hold('Semantic Scholar недоступен: %s' % str(ex)[:80], data=[]))

app = web.Application()
for p, h in (('/api/training/status', training), ('/api/nox/activity', activity), ('/api/notifications', notifications), ('/api/nox/status', status)):
    app.router.add_get(p, h)
app.router.add_get('/api/nox/training/status', training)
app.router.add_get('/api/sci/arxiv', sci_arxiv)
app.router.add_get('/api/sci/semantic', sci_semantic)
app.router.add_get('/api/nox/self_now', self_now)
app.router.add_get('/api/nox/briefs', briefs)
app.router.add_route('*', '/api/settings', settings)
if __name__ == '__main__':
    web.run_app(app, host='127.0.0.1', port=PORT, print=None)
