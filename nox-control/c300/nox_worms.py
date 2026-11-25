"""Черви-лайт (канон v5 гл. 9): поиск с квотами и белым списком, карантин находок, охота только по «Разрешаешь?»,
голод (>1 ч, >24 ч, >7 дн), самоулучшение с откатом, «чему я научился», утренние идеи (08:00 МСК). STOP за <=10 с: файл state/worms_stop."""
import os, re, json, time, sqlite3, threading, hashlib, shutil, urllib.request, urllib.parse
W = '/workspace/nox'; ST = W + '/state'; STAGE = W + '/worm_staging'; DB = W + '/agents/worms.sqlite'
LICENSE_OK = {'apache-2.0', 'mit', 'bsd-3-clause', 'bsd-2-clause', 'cc-by-4.0', 'cc0-1.0', 'unlicense', 'openrail', 'gemma'}   # NC и «other» только по решению Создателя
BAD_EXT = ('.bin', '.pt', '.pth', '.pkl', '.pickle', '.ckpt', '.joblib', '.npy')
GOOD_EXT = ('.gguf', '.safetensors')
QUOTA_DEFAULT = {'hf_per_hour': 20, 'github_per_hour': 8, 'rss_per_hour': 6}
TOPICS = ['Qwen coder GGUF', 'UI generation Qwen', 'Russian LLM GGUF', 'tiny LLM router classifier', 'reranker GGUF']
RSS = ['https://huggingface.co/blog/feed.xml']   # белый список лент
_c = sqlite3.connect(DB, check_same_thread=False); _c.row_factory = sqlite3.Row; _l = threading.RLock()
def q(s, a=(), one=False):
    with _l:
        cur = _c.execute(s, a); _c.commit(); return cur.fetchone() if one else cur.fetchall()
q('CREATE TABLE IF NOT EXISTS finds(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, src TEXT, name TEXT, url TEXT, license TEXT, size_gb REAL, files TEXT, verdict TEXT, score REAL, status TEXT, sha TEXT, note TEXT, UNIQUE(src,name))')
q('CREATE TABLE IF NOT EXISTS cands(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, title TEXT, payload TEXT, status TEXT, backup TEXT)')
q('CREATE TABLE IF NOT EXISTS learned(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, text TEXT)')
q('CREATE TABLE IF NOT EXISTS ideas(id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT, ts REAL, title TEXT, why TEXT, status TEXT)')
q('CREATE TABLE IF NOT EXISTS quota(k TEXT, hour TEXT, n INT, PRIMARY KEY(k,hour))')
def jl(p, d):
    try: return json.load(open(p))
    except Exception: return d
def stopped(): return os.path.exists(ST + '/worms_stop')
def spend(k):
    h = time.strftime('%Y%m%d%H'); lim = jl(ST + '/worms_quota.json', QUOTA_DEFAULT).get(k, 5)
    r = q('SELECT n FROM quota WHERE k=? AND hour=?', (k, h), one=True)
    if r and r['n'] >= lim: return False
    q('INSERT INTO quota VALUES(?,?,1) ON CONFLICT(k,hour) DO UPDATE SET n=n+1', (k, h)); return True
def http(url, t=20):
    rq = urllib.request.Request(url, headers={'User-Agent': 'nox-worm/1'}); return urllib.request.urlopen(rq, timeout=t).read()

def free_gb():
    s = os.statvfs('/workspace'); return s.f_bavail * s.f_frsize / 1e9
def judge_text(llm, name, desc):
    try:
        r = llm('judge_llm', 'Оцени находку для проекта NOX (локальный ИИ: код, UI, русский, нано-классификаторы). JSON {"score":1-10,"why":"кратко"}', f'{name}\n{desc}'[:1200], 120, 0.0, None, 90)
        m = re.search(r'\{.*\}', r, re.S); j = json.loads(m.group(0)) if m else {}; return float(j.get('score', 0)), str(j.get('why', ''))[:160]
    except Exception: return None, 'судья недоступен'

def quarantine(model_json):
    """Только safetensors/GGUF, без pickle, чистая лицензия. Возвращает (ok, причина, файлы, размер)."""
    sib = [s.get('rfilename', '') for s in model_json.get('siblings', [])]
    if any(f.lower().endswith(BAD_EXT) for f in sib): return False, 'есть pickle/бинарные веса', [], 0
    good = [f for f in sib if f.lower().endswith(GOOD_EXT)]
    if not good: return False, 'нет safetensors/GGUF', [], 0
    lic = (model_json.get('cardData') or {}).get('license') or next((t.split(':')[1] for t in model_json.get('tags', []) if t.startswith('license:')), 'unknown')
    if str(lic).lower() not in LICENSE_OK: return False, f'лицензия {lic} не в белом списке (NC/другая — только решение Создателя)', good, 0
    return True, f'лицензия {lic}', good, 0

def hf_scan(llm):
    n = 0
    for topic in TOPICS:
        if stopped() or not spend('hf_per_hour'): break
        try: items = json.loads(http('https://huggingface.co/api/models?' + urllib.parse.urlencode({'search': topic, 'sort': 'downloads', 'limit': 6, 'full': 'true'})))
        except Exception: continue
        for m in items:
            if stopped(): return n
            name = m.get('modelId') or m.get('id')
            if q('SELECT 1 FROM finds WHERE src="hf" AND name=?', (name,), one=True): continue
            ok, why, files, _ = quarantine(m)
            sc, jw = judge_text(llm, name, f'теги: {m.get("tags", [])[:12]}; {why}') if ok else (0.0, '')
            if sc is None:   # судья недоступен: не отклонять, а оценить по популярности (дёшево и честно помечено)
                dl = int(m.get('downloads') or 0); sc = 7.0 if dl > 50000 else 6.0 if dl > 5000 else 4.0; jw = f'эвристика: {dl} загрузок (судья недоступен)'
            q('INSERT OR IGNORE INTO finds(ts,src,name,url,license,size_gb,files,verdict,score,status,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
              (time.time(), 'hf', name, 'https://huggingface.co/' + name, why, 0, json.dumps(files[:6]), 'допущено' if ok else 'отклонено: ' + why, sc, 'candidate' if ok and sc >= 6 else 'rejected', jw)); n += 1
    return n
def gh_scan(llm):
    n = 0
    if stopped() or not spend('github_per_hour'): return 0
    try: items = json.loads(http('https://api.github.com/search/repositories?q=llm+agent+license:apache-2.0+language:python&sort=stars&per_page=5'))['items']
    except Exception: return 0
    for r in items:
        name = r['full_name']
        if q('SELECT 1 FROM finds WHERE src="github" AND name=?', (name,), one=True): continue
        sc, jw = judge_text(llm, name, r.get('description') or '')
        q('INSERT OR IGNORE INTO finds(ts,src,name,url,license,verdict,score,status,note) VALUES(?,?,?,?,?,?,?,?,?)', (time.time(), 'github', name, r['html_url'], (r.get('license') or {}).get('spdx_id', '?'), 'допущено', sc, 'candidate' if sc >= 6 else 'rejected', jw)); n += 1
    return n
def rss_scan(llm):
    if stopped() or not spend('rss_per_hour'): return 0
    n = 0
    for u in RSS:
        try: x = http(u).decode('utf8', 'ignore')
        except Exception: continue
        for t, l in re.findall(r'<title>(.*?)</title>\s*<link[^>]*?(?:href=")?(https?://[^"<\s]+)', x, re.S)[1:4]:
            if q('SELECT 1 FROM finds WHERE src="rss" AND name=?', (t[:150],), one=True): continue
            q('INSERT OR IGNORE INTO finds(ts,src,name,url,verdict,score,status) VALUES(?,?,?,?,?,?,?)', (time.time(), 'rss', t[:150], l, 'новость', 5, 'info')); n += 1
    return n

# ---- голод и охота ----
def last_absorb():
    r = q('SELECT max(ts) t FROM finds WHERE status="absorbed"', one=True); return (r['t'] if r and r['t'] else jl(ST + '/worms_state.json', {}).get('born', time.time() - 3600 * 2))
def hunger():
    h = (time.time() - last_absorb()) / 3600
    return {'hours': round(h, 1), 'level': 3 if h > 168 else 2 if h > 24 else 1 if h > 1 else 0, 'active_search': h > 24}
def hunger_phrase():
    st = jl(ST + '/worms_state.json', {}); h = hunger()
    if h['level'] and time.strftime('%Y%m%d') != st.get('phrase_day'):
        st['phrase_day'] = time.strftime('%Y%m%d'); json.dump(st, open(ST + '/worms_state.json', 'w')); return ['', 'Мне нужны данные.', 'Я голоден: больше суток без нового. Ищу сам.', 'Я очень голоден: больше недели без поглощения.'][h['level']]
    return ''
def cards():
    return [{'id': r['id'], 'text': f'Нашёл {r["name"]}. Хочу поглотить. Разрешаешь?', 'license': r['license'], 'url': r['url'], 'files': json.loads(r['files'] or '[]'), 'score': r['score'], 'why': r['note'], 'actions': ['Разрешаю', 'Нет']}
            for r in q('SELECT * FROM finds WHERE status="candidate" AND src="hf" ORDER BY score DESC LIMIT 5')]
def approve(fid, yes):
    r = q('SELECT * FROM finds WHERE id=?', (fid,), one=True)
    if not r or r['status'] != 'candidate': return {'ok': False, 'error': 'нет такой карточки'}
    if not yes: q('UPDATE finds SET status="declined" WHERE id=?', (fid,)); return {'ok': True, 'status': 'declined'}
    if free_gb() < 20: return {'ok': False, 'error': f'свободно {free_gb():.0f} ГБ, нужно >=20 после загрузки'}
    q('UPDATE finds SET status="downloading" WHERE id=?', (fid,)); threading.Thread(target=_download, args=(fid,), daemon=True).start(); return {'ok': True, 'status': 'downloading'}
def _download(fid):
    r = q('SELECT * FROM finds WHERE id=?', (fid,), one=True); files = json.loads(r['files'] or '[]'); d = os.path.join(STAGE, r['name'].replace('/', '__')); os.makedirs(d, exist_ok=True)
    f = sorted(files, key=lambda x: ('q4_k_m' not in x.lower(), len(x)))[0] if files else None; sha = ''
    try:
        if not f: raise RuntimeError('нет файлов')
        url = f'https://huggingface.co/{r["name"]}/resolve/main/{urllib.parse.quote(f)}'; out = os.path.join(d, os.path.basename(f)); h = hashlib.sha256()
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'nox-worm/1'}), timeout=60) as resp, open(out + '.part', 'wb') as fo:
            while True:
                if stopped(): raise RuntimeError('STOP')
                b = resp.read(1 << 22)
                if not b: break
                fo.write(b); h.update(b)
                if free_gb() < 15: raise RuntimeError('диск <15 ГБ, остановлено')
        os.replace(out + '.part', out); sha = h.hexdigest()
        q('UPDATE finds SET status="absorbed", sha=?, note=note||? WHERE id=?', (sha, f' | staging {out}', fid)); history(f'Поглощено в staging: {r["name"]} / {f}, sha256 {sha[:16]}')
    except Exception as e:
        q('UPDATE finds SET status="failed", note=note||? WHERE id=?', (' | ' + str(e)[:100], fid)); history(f'Не вышло: {r["name"]}: {e}')
def history(t):
    q('INSERT INTO learned(ts,text) VALUES(?,?)', (time.time(), t)); open(ST + '/worms_history.jsonl', 'a').write(json.dumps({'ts': int(time.time()), 'text': t}, ensure_ascii=False) + '\n')

# ---- самоулучшение: ошибки -> кандидат -> проверка -> «Разрешаешь?» -> применение с откатом ----
def self_candidates(book_sql):
    n = 0
    for r in book_sql('SELECT task,text FROM steps WHERE kind="review" AND text LIKE "ВОЗВРАТ%" ORDER BY id DESC LIMIT 40'):
        reason = r['text'].split('|')[-1].strip()[:140]
        if len(reason) < 12 or q('SELECT 1 FROM cands WHERE title=?', ('Правило ревизора: ' + reason,), one=True): continue
        q('INSERT INTO cands(ts,kind,title,payload,status) VALUES(?,?,?,?,"proposed")', (time.time(), 'rule', 'Правило ревизора: ' + reason, json.dumps({'rule': reason}, ensure_ascii=False))); n += 1
        if n >= 3: break
    return n
def test_candidate(c):      # песочница: кандидат-правило проверяется на валидность и отсутствие запрещённого
    p = json.loads(c['payload']); ok = bool(p.get('rule')) and not re.search(r'rm |sudo|pickle|удали', p['rule'], re.I)
    q('UPDATE cands SET status=? WHERE id=?', ('tested' if ok else 'rejected', c['id'])); return ok
def self_cards():
    for c in q('SELECT * FROM cands WHERE status="proposed"'): test_candidate(c)
    return [{'id': c['id'], 'text': f'Хочу улучшить себя: {c["title"]}. Разрешаешь?', 'actions': ['Разрешаю', 'Нет']} for c in q('SELECT * FROM cands WHERE status="tested" LIMIT 5')]
def self_apply(cid, yes):
    c = q('SELECT * FROM cands WHERE id=?', (cid,), one=True)
    if not c or c['status'] != 'tested': return {'ok': False}
    if not yes: q('UPDATE cands SET status="declined" WHERE id=?', (cid,)); return {'ok': True, 'status': 'declined'}
    p = ST + '/owner_intents.json'; bk = p + f'.bak_self_{cid}'; shutil.copy(p, bk)
    d = jl(p, {}); d.setdefault('_reviewer_rules', []).append(json.loads(c['payload'])['rule']); json.dump(d, open(p, 'w'), ensure_ascii=False, indent=1)
    q('UPDATE cands SET status="applied", backup=? WHERE id=?', (bk, cid)); history('Научился: ' + c['title']); return {'ok': True, 'status': 'applied', 'rollback': f'/worms/self/rollback/{cid}'}
def self_rollback(cid):
    c = q('SELECT * FROM cands WHERE id=?', (cid,), one=True)
    if not c or c['status'] != 'applied' or not os.path.exists(c['backup'] or ''): return {'ok': False}
    shutil.copy(c['backup'], ST + '/owner_intents.json'); q('UPDATE cands SET status="rolled_back" WHERE id=?', (cid,)); history('Откат: ' + c['title']); return {'ok': True}

# ---- сон и утренняя повестка ----
def dream_text():
    try: lines = open(ST + '/mind/dream.jsonl').read().strip().split('\n')[-3:]; return ' '.join(json.loads(x).get('dream', '') for x in lines)[:900]
    except Exception: return ''
def make_agenda(llm):
    day = time.strftime('%Y%m%d')
    if q('SELECT 1 FROM ideas WHERE day=?', (day,), one=True): return 0
    finds = '; '.join(f'{r["name"]} ({r["score"]})' for r in q('SELECT name,score FROM finds WHERE status IN ("candidate","absorbed") ORDER BY score DESC LIMIT 5'))
    learned = '; '.join(r['text'][:80] for r in q('SELECT text FROM learned ORDER BY id DESC LIMIT 4'))
    out = llm('main', 'Ты NativeIdeaLoop. Дай 3-5 идей дня для развития NOX, каждая одной строкой «название — зачем». Только список.', f'Сон: {dream_text()}\nНаходки червей: {finds}\nНедавно узнал: {learned}', 400, 0.7, None, 240)
    n = 0
    for l in [x.strip('-*• 0123456789.)') for x in out.split('\n') if len(x.strip()) > 8][:5]:
        t, _, w = l.partition('—'); q('INSERT INTO ideas(day,ts,title,why,status) VALUES(?,?,?,?,"new")', (day, time.time(), t.strip()[:120], w.strip()[:200])); n += 1
    return n

# ---- пастух: цикл под диспетчером, ниже чата и задач ----
HB = ST + '/worms_hb.json'
def shepherd(llm, busy, book_sql, running=lambda: 0):
    last_scan = 0
    while True:
        try:
            json.dump({'ts': int(time.time()), 'stopped': stopped(), 'hunger': hunger()}, open(HB, 'w'))
            if not stopped() and not busy() and running() == 0 and not os.path.exists(ST + '/orch/chat_hold'.replace('chat_hold', 'chat_hold_now')):
                period = 900 if hunger()['active_search'] else 3600
                if time.time() - last_scan > period:
                    last_scan = time.time(); hf_scan(llm); gh_scan(llm); rss_scan(llm); self_candidates(book_sql)
                if time.strftime('%H') >= '08' and time.strftime('%H') < '12': make_agenda(llm)
        except Exception as e: open(W + '/agents/worms.err', 'a').write(repr(e)[:300] + '\n')
        time.sleep(5)

def mount(app, llm, busy, book_sql, new_task, running):
    from fastapi import Request
    @app.get('/worms')
    def w_state(): return {'hunger': hunger(), 'phrase': hunger_phrase(), 'stopped': stopped(), 'finds': [dict(r) for r in q('SELECT id,src,name,license,score,status,verdict FROM finds ORDER BY id DESC LIMIT 30')], 'quota': jl(ST + '/worms_quota.json', QUOTA_DEFAULT)}
    @app.get('/worms/cards')
    def w_cards(): return {'hunt': cards(), 'self': self_cards()}
    @app.post('/worms/approve')
    async def w_ap(req: Request): b = await req.json(); return approve(int(b['id']), bool(b.get('yes')))
    @app.post('/worms/self/approve')
    async def w_sa(req: Request): b = await req.json(); return self_apply(int(b['id']), bool(b.get('yes')))
    @app.post('/worms/self/rollback/{cid}')
    def w_rb(cid: int): return self_rollback(cid)
    @app.get('/worms/learned')
    def w_l(): return [dict(r) for r in q('SELECT ts,text FROM learned ORDER BY id DESC LIMIT 30')]
    @app.get('/worms/agenda')
    def w_ag(): return {'dream': dream_text(), 'ideas': [dict(r) for r in q('SELECT id,day,title,why,status FROM ideas ORDER BY id DESC LIMIT 5')]}
    @app.post('/worms/agenda/make')
    def w_mk(): return {'made': make_agenda(llm)}
    @app.post('/worms/develop')
    async def w_dev(req: Request):
        b = await req.json(); r = q('SELECT * FROM ideas WHERE id=?', (int(b['id']),), one=True)
        if not r: return {'ok': False}
        q('UPDATE ideas SET status="developing" WHERE id=?', (r['id'],)); return {'ok': True, 'task': new_task('Идея дня: ' + r['title'][:50], f'Разверни идею и сделай рабочий набросок: {r["title"]} — {r["why"]}', 'writer', None, 'ideas')}
    @app.post('/worms/scan')
    def w_scan(): return {'hf': hf_scan(llm), 'github': gh_scan(llm), 'rss': rss_scan(llm), 'self': self_candidates(book_sql)}
    @app.post('/worms/stop')
    def w_stop(): open(ST + '/worms_stop', 'w').write(str(time.time())); return {'stopped': True}
    @app.post('/worms/start')
    def w_start():
        try: os.remove(ST + '/worms_stop')
        except FileNotFoundError: pass
        return {'stopped': False}
    threading.Thread(target=shepherd, args=(llm, busy, book_sql, running), daemon=True).start()
