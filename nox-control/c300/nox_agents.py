#!/usr/bin/env python3
"""NOX субисполнители: книга задач (SQLite), диспетчер-1, планировщик, исполнители, ревизор, тренер, консилиум, карточка.
Порт 8810, только 127.0.0.1. Песочница /workspace/nox/agents/<id>. Без rm вне песочницы, без sudo."""
import asyncio, os, re, json, time, sqlite3, threading, subprocess, hashlib, shutil, sys, queue, uuid, html.parser
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
W = '/workspace/nox'; A = W + '/agents'; DB = A + '/book.sqlite'; SB = A + '/sandbox'
ST = W + '/state'; PORT = 8810
os.makedirs(SB, exist_ok=True)

def jload(p, d):
    try: return json.load(open(p))
    except Exception: return d
ROLES = lambda: jload(ST + '/agent_roles.json', {})
BACK = lambda: jload(ST + '/agent_backends.json', {})
TEAMS = lambda: jload(ST + '/teams.json', {})
INTENTS = lambda: jload(ST + '/owner_intents.json', {})

_db_lock = threading.RLock()
def db():
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False); c.row_factory = sqlite3.Row; return c
CON = db()
try: CON.execute('ALTER TABLE tasks ADD COLUMN prio INT DEFAULT 0'); CON.commit()
except Exception: pass
def sql(q, a=(), one=False):
    with _db_lock:
        cur = CON.execute(q, a); CON.commit()
        r = cur.fetchone() if one else cur.fetchall()
        return r
with _db_lock:
    CON.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, title TEXT, goal TEXT, role TEXT, team TEXT, project TEXT, status TEXT, created REAL, started REAL, finished REAL, hb REAL, restarts INT DEFAULT 0, plan TEXT, result TEXT, first_pass INT, returns INT DEFAULT 0, tokens INT DEFAULT 0, spec TEXT);
    CREATE TABLE IF NOT EXISTS steps(id INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT, ts REAL, kind TEXT, role TEXT, text TEXT);
    CREATE TABLE IF NOT EXISTS lease(k TEXT PRIMARY KEY, owner TEXT, ts REAL);
    ''')

def step(tid, kind, text, role=''):
    sql('INSERT INTO steps(task,ts,kind,role,text) VALUES(?,?,?,?,?)', (tid, time.time(), kind, role, str(text)[:4000]))
    sql('UPDATE tasks SET hb=? WHERE id=?', (time.time(), tid))
    EV.put({'task': tid, 'kind': kind, 'role': role, 'text': str(text)[:300]})
EV = queue.Queue(maxsize=1000)

# ---------- LLM клиент с лимитом слотов ----------
SEM = {}; SEMLOCK = threading.Lock()
class PSem:
    """семафор с приоритетом: сначала задачи из чата (prio 10), потом обычные, потом golden/идеи"""
    def __init__(self, n): self.n = n; self.c = threading.Condition(); self.q = []; self.seq = 0
    def acquire(self, prio=0):
        with self.c:
            self.seq += 1; me = (-prio, self.seq); self.q.append(me); self.q.sort()
            while not (self.n > 0 and self.q[0] == me): self.c.wait(5)
            self.q.pop(0); self.n -= 1
    def release(self):
        with self.c: self.n += 1; self.c.notify_all()
def _prio(tid):
    try: return (sql('SELECT prio FROM tasks WHERE id=?', (tid,), one=True) or {'prio': 0})['prio'] or 0
    except Exception: return 0
def sem(name):
    with SEMLOCK:
        if name not in SEM: SEM[name] = PSem(int(BACK().get(name, {}).get('slots', 1)))
        return SEM[name]
def chat_busy():
    try: return time.time() - os.path.getmtime(ST + '/orch/chat_hold') < 6
    except Exception: return False
DOWN = {}   # backend -> ts последнего отказа (предохранитель 180 с)
def llm(backend, system, user, max_tokens=1500, temp=0.3, tid=None, timeout=420):
    b = BACK().get(backend) or BACK()['main']
    s = sem(backend if backend in BACK() else 'main'); s.acquire(_prio(tid) if tid else 0)
    try:
        for _ in range(60):          # чат важнее: уступаем, пока идёт ход чата (только для общей основной модели)
            if b.get('yield_chat') and chat_busy(): time.sleep(2)
            else: break
        body = {'model': b.get('model', 'x'), 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                'max_tokens': max_tokens, 'temperature': temp, 'chat_template_kwargs': {'enable_thinking': False}}
        hdr = {'Content-Type': 'application/json'}
        if b.get('key_env') and os.environ.get(b['key_env']): hdr['Authorization'] = 'Bearer ' + os.environ[b['key_env']]
        try:
            if backend != 'external' and BACK().get('external') and time.time() - DOWN.get(backend, 0) < 180: raise RuntimeError('breaker: локальная модель недавно не отвечала')
            r = httpx.post(b['url'].rstrip('/') + '/chat/completions', json=body, headers=hdr, timeout=min(timeout, 100) if backend != 'external' else timeout)
            r.raise_for_status(); j = r.json()
        except Exception as e:
            if backend != 'external' and 'breaker' not in str(e): DOWN[backend] = time.time()      # локальная модель занята/недоступна: не виснуть, уйти к внешним советникам (шлюз :8793, с очисткой личного)
            gw = BACK().get('external')
            if not gw or backend == 'external': raise
            if tid: step(tid, 'fallback', f'{backend} недоступен ({type(e).__name__}), иду к внешним советникам', 'dispatcher')
            r = httpx.post(gw['url'].rstrip('/') + '/chat/completions', json={'model': 'auto', 'messages': body['messages'], 'max_tokens': min(max_tokens, 1800), 'temperature': temp}, timeout=150)
            r.raise_for_status(); j = r.json()
        if tid: sql('UPDATE tasks SET tokens=tokens+? WHERE id=?', (int(j.get('usage', {}).get('completion_tokens', 0)), tid))
        t = j['choices'][0]['message'].get('content') or ''
        return re.sub(r'<think>.*?</think>', '', t, flags=re.S).strip()
    finally: s.release()

def jparse(t, default=None):
    m = re.search(r'\{.*\}', t, re.S)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    return default

# ---------- песочница и инструменты (белый список) ----------
def safe_path(root, rel):
    rel = rel.strip().lstrip('/').replace('\\', '/')
    p = os.path.normpath(os.path.join(root, rel))
    if not p.startswith(root + os.sep) or '..' in rel.split('/'): raise ValueError('путь вне песочницы: ' + rel)
    return p
def write_files(root, text):
    names = []
    for m in re.finditer(r'###\s*FILE:\s*(\S+)\s*\n(.*?)(?=\n###\s*FILE:|\Z)', text, re.S):
        body = m.group(2).strip('\n')
        body = re.sub(r'^```[a-zA-Z0-9]*\n', '', body); body = re.sub(r'\n```\s*$', '', body)
        try: p = safe_path(root, m.group(1))
        except ValueError: continue
        os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(body + '\n'); names.append(m.group(1))
    return names
def run_pytest(root, timeout=60):
    env = {'PATH': '/usr/bin:/bin:' + os.path.dirname(sys.executable), 'HOME': root, 'PYTHONDONTWRITEBYTECODE': '1'}
    try:
        r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-x', '--tb=short', '-p', 'no:cacheprovider'], cwd=root, env=env, capture_output=True, text=True, timeout=timeout,
                           preexec_fn=lambda: __import__('resource').setrlimit(__import__('resource').RLIMIT_AS, (4 << 30, 4 << 30)))
        return r.returncode == 0, (r.stdout + r.stderr)[-1500:]
    except subprocess.TimeoutExpired: return False, 'timeout pytest'
class _H(html.parser.HTMLParser):
    def __init__(s): super().__init__(); s.tags = []; s.ids = set(); s.txt = ''
    def handle_starttag(s, t, a): s.tags.append(t); [s.ids.add(v) for k, v in a if k == 'id' and v]
    def handle_data(s, d): s.txt += d

# ---------- Паспорт намерения и сверка плана (роли на тех же моделях) ----------
VERBS = [('stop', r'останов|прекрати|заверши работу|отмени'), ('replace', r'замени|вместо'), ('move', r'перенес|перенеси'), ('delete', r'удали|сотри'),
         ('add', r'добав|допиши|подключи|сделай ещ'), ('split', r'раздел|раскидай|по очеред'), ('speed', r'ускор|быстрее'), ('finish', r'доведи|заверши|доделай'),
         ('download', r'скачай|загрузи')]
def passport(text, fast=False):
    low = text.lower(); verbs = [v for v, rx in VERBS if re.search(rx, low)]
    keep_cur = bool(re.search(r'не останавлива|текущее не|не трогай|не прерывай|продолжай|не переноси|не снижай', low)) or not re.search(r'останов|замени|перенес|прекрати|отмени', low)
    p = {'verbs': verbs, 'verb': verbs[0] if verbs else 'other', 'stop_current': False if keep_cur else True, 'keep': ['текущая работа продолжается'] if keep_cur else [],
         'constraints': [m.group(0) for m in re.finditer(r'(не [а-яё]+(?: [а-яё]+)?)', low)][:6], 'raw': text, 'ambiguous': False}
    if 'add' in verbs and not re.search(r'останов|замени|перенес', low): p['stop_current'] = False; p['verb'] = 'add'
    if 'split' in verbs and 'add' not in verbs: p['scope'] = 'только новое; текущее не трогать'
    try:
        if fast: raise ValueError('fast')
        j = jparse(llm('judge_llm', 'Разбери команду владельца в JSON: {"object":"что","scope":"объём","done_when":"критерий готовности","keep":["что остаётся как есть"],"constraints":["запреты"]}. «Добавь» не значит «замени/останови/перенеси». Молчание о текущей работе = продолжать её. Только JSON.', text, 250, 0.0, None, 120), {}) or {}
        for k in ('object', 'scope', 'done_when'): p[k] = j.get(k, p.get(k, ''))
        p['keep'] = list(dict.fromkeys(p['keep'] + [str(x) for x in j.get('keep', [])][:5])); p['constraints'] = list(dict.fromkeys(p['constraints'] + [str(x) for x in j.get('constraints', [])][:5]))
    except Exception: pass
    return p
def plan_drift(pp, plan_obj, text):
    txt = json.dumps(plan_obj, ensure_ascii=False).lower(); reasons = []
    if not pp.get('stop_current') and re.search(r'останов|перенест|отмен|замен|удал', txt): reasons.append('в плане остановка/перенос/замена, о которых не просили')
    if pp.get('verb') == 'add' and re.search(r'вместо|заменить', txt): reasons.append('«добавь» превращено в «замени»')
    try:
        j = jparse(llm('main', 'Сверь план с исходной фразой владельца и паспортом. Ищи дрейф: сужение объёма, остановку или перенос того, о чём не просили, снижение планки, подмену цели. Верни JSON {"drift":true|false,"reason":"кратко"}.', f'Фраза: {text}\nПаспорт: {json.dumps(pp, ensure_ascii=False)[:800]}\nПлан: {json.dumps(plan_obj, ensure_ascii=False)[:1500]}', 150, 0.0, None, 200), {}) or {}
        if j.get('drift'): reasons.append(str(j.get('reason', 'дрейф'))[:150])
    except Exception: pass
    return reasons
def save_correction(said, understood, wanted):
    d = INTENTS(); d.setdefault('_corrections', []).append({'ts': int(time.time()), 'said': said, 'understood': understood, 'wanted': wanted})
    json.dump(d, open(ST + '/owner_intents.json', 'w'), ensure_ascii=False, indent=1)
    lesson('owner', f'понял: {understood}', f'владелец сказал: {said}', f'надо: {wanted}', 'owner')

# ---------- Planner (1 вызов основной модели) ----------
def expand_intent(goal):
    hints = []
    for k, v in INTENTS().items():
        if k.lower() in goal.lower(): hints.append(f'«{k}» = {v["action"]}' + (' [ПЕРЕСПРОС ТОЛЬКО ЕСЛИ ДОРОГАЯ ОШИБКА]' if v.get('costly') else ''))
    return hints
def plan(t):
    roles = ROLES(); rl = ', '.join(f'{k} ({v["desc"]})' for k, v in roles.items() if v.get('kind') != 'service')
    hints = expand_intent(t['goal'] + ' ' + t['title'])
    forced = None
    if t['team']:
        forced = TEAMS().get(t['team'])
    if t['role']:
        return {'goal': t['goal'], 'done_if': 'артефакт создан и принят ревизором', 'subtasks': [{'id': 's1', 'role': t['role'], 'task': t['goal'], 'deps': []}], 'note': 'роль задана'}
    sysmsg = 'Ты планировщик. Верни ТОЛЬКО JSON: {"goal":"...","done_if":"проверяемое условие","subtasks":[{"id":"s1","role":"<роль>","task":"...","deps":[]}]}. Не более 4 подзадач, минимум достаточно. Роли: ' + rl
    u = f'Задача: {t["title"]}\nЦель: {t["goal"]}\nИнтерпретации команд владельца: {hints or "нет"}\n' + (f'Команда: {forced}' if forced else '')
    pp = passport(t['goal'] + ' ' + t['title']); step(t['id'], 'passport', json.dumps(pp, ensure_ascii=False)[:700], 'advisor')
    corr = INTENTS().get('_corrections', [])[-5:]
    if corr: u += '\nПрошлые поправки владельца (учти): ' + json.dumps(corr, ensure_ascii=False)[:600]
    u += f'\nПаспорт намерения: {json.dumps(pp, ensure_ascii=False)[:800]}. «добавь» не значит «останови/перенеси/замени»; текущее не трогай, если не просили.'
    try:
        for rnd in range(3):
            p = jparse(llm('main', sysmsg, u, 700, 0.2, t['id']))
            if not (p and p.get('subtasks')): break
            for s in p['subtasks']:
                if s.get('role') not in roles: s['role'] = 'writer'
            p['interpreted'] = hints; p['passport'] = pp
            dr = plan_drift(pp, p, t['goal'])
            step(t['id'], 'plan_check', 'дрейф: ' + '; '.join(dr) if dr else 'дрейфа нет', 'advisor')
            if not dr: return p
            u += '\nДРЕЙФ ПЛАНА, исправь: ' + '; '.join(dr)
        if p and p.get('subtasks'): p['question'] = 'Уточни одним словом: что именно сделать с текущей работой — продолжать или менять?'; return p
    except Exception as e: step(t['id'], 'warn', 'planner: ' + str(e)[:200])
    return {'goal': t['goal'], 'done_if': 'артефакт создан', 'subtasks': [{'id': 's1', 'role': 'coder' if re.search(r'код|python|функци|скрипт', t['goal'], re.I) else 'writer', 'task': t['goal'], 'deps': []}], 'note': 'планировщик недоступен, один шаг'}

# ---------- исполнитель ----------

# ---------- Доведение и самоулучшение: уроки (S03/Reflexion), карточка, инспектор ----------
LESS = ST + '/lessons.jsonl'; PAIRS = ST + '/night_pairs.jsonl'; NUDGE = {}; STALL = {}; REPEAT = {'n': 0, 'lessons': 0}
STALL_MIN = float(os.environ.get('NOX_STALL_MIN', '15'))
def _norm(x): return re.sub(r'[^a-zа-яё0-9]+', ' ', x.lower())[:90].strip()
def lesson(tid, what, why, rule, src='task'):
    """Reflexion: что случилось -> почему -> правило. В S03-файл, в плейбук (бриф всем следующим), в пары для ночного обучения."""
    try:
        key = _norm(rule); seen = [json.loads(l) for l in open(LESS)] if os.path.exists(LESS) else []
        dup = [x for x in seen if _norm(x['rule']) == key]
        rec = {'ts': int(time.time()), 'task': tid, 'src': src, 'what': str(what)[:300], 'why': str(why)[:300], 'rule': str(rule)[:300], 'repeat': len(dup)}
        open(LESS, 'a').write(json.dumps(rec, ensure_ascii=False) + '\n'); REPEAT['lessons'] += 1
        if dup:
            REPEAT['n'] += 1; step(tid, 'lesson', 'ПОВТОР ошибки (правило уже было): ' + rule[:120], 'inspector')
            return
        os.makedirs(PB, exist_ok=True)
        open(PB + '/_lessons.yaml', 'a').write('- ' + rec['rule'].replace('\n', ' ') + '\n')
        open(PAIRS, 'a').write(json.dumps({'prompt': rec['what'], 'response': rec['rule'], 'why': rec['why']}, ensure_ascii=False) + '\n')
        step(tid, 'lesson', f'урок: {what[:80]} -> {rule[:100]}', 'inspector')
    except Exception as e: print('lesson err', e, flush=True)
def lessons_text(n=12):
    try: return '\n'.join(open(PB + '/_lessons.yaml').read().strip().splitlines()[-n:])
    except Exception: return ''
STAGES = {'plan': 'планирование', 'passport': 'планирование', 'plan_check': 'планирование', 'brief': 'выполнение', 'exec': 'выполнение', 'review': 'проверка', 'coach': 'коррекция', 'trainer': 'коррекция', 'search': 'поиск решения', 'stopper': 'стопор', 'escalate': 'эскалация', 'lesson': 'урок', 'final': 'готово'}
def card(tid):
    r = sql('SELECT * FROM tasks WHERE id=?', (tid,), one=True)
    if not r: return None
    st = [dict(x) for x in sql('SELECT ts,kind,role,text FROM steps WHERE task=? ORDER BY id', (tid,))]
    pl = jload(r['plan'] or '', None) or {}; subs = pl.get('subtasks', []) if isinstance(pl, dict) else []
    acc = sum(1 for x in st if x['kind'] == 'review' and x['text'].startswith('ПРИНЯТО')); tot = max(len(subs), 1)
    pct = 100 if r['status'] == 'done' else min(95, int(100 * acc / tot)) if subs else (5 if st else 0)
    stop = next((x['text'][:200] for x in reversed(st) if x['kind'] in ('stopper', 'coach', 'escalate')), '')
    if r['status'] in ('done', 'needs_owner'): stop = stop if r['status'] == 'needs_owner' else ''
    last = st[-1] if st else {'kind': 'queued', 'text': '', 'ts': r['created']}
    el = (time.time() - (r['started'] or r['created'])) if r['status'] != 'done' else ((r['finished'] or 0) - (r['started'] or 0))
    eta = int(el / pct * (100 - pct)) if r['status'] == 'running' and pct >= 20 else 0
    col = 'Отменено' if r['status'] == 'cancelled' else 'Готово' if r['status'] == 'done' else 'Нужен ты' if r['status'] in ('needs_owner', 'failed') else 'В работе' if r['status'] == 'running' else 'Очередь'
    return {'id': tid, 'title': r['title'], 'column': col, 'stage': STAGES.get(last['kind'], last['kind']), 'blocker': stop, 'doing': f"{last['kind']}: {last['text'][:140]}", 'pct': pct, 'eta_sec': eta, 'idle_sec': int(time.time() - last['ts'])}
def stall_check():
    """нет шагов N минут -> толчок коуча -> смена подхода -> эскалация диспетчеру (перезапуск/Нужен ты)"""
    for r in sql('SELECT id FROM tasks WHERE status="running"'):
        tid = r['id']; last = sql('SELECT MAX(ts) m FROM steps WHERE task=?', (tid,), one=True)['m'] or 0
        idle = (time.time() - last) / 60; lvl = STALL.get(tid, 0)
        if tid not in RUNNING: continue
        if idle < STALL_MIN: STALL[tid] = 0; continue
        want = 3 if idle >= 3 * STALL_MIN else 2 if idle >= 2 * STALL_MIN else 1
        if want <= lvl: continue
        STALL[tid] = want; COACH['n'] += 1
        if want == 1: NUDGE[tid] = 'нет прогресса: упрости шаг, выдай рабочий черновик'; step(tid, 'coach', f'нет прогресса {idle:.0f} мин: толчок', 'coach')
        elif want == 2: NUDGE[tid] = 'смени подход: пересоздай с нуля, возьми готовое'; step(tid, 'coach', 'нет прогресса: смена подхода', 'coach')
        else:
            step(tid, 'escalate', f'нет прогресса {idle:.0f} мин: эскалация диспетчеру, перезапуск', 'dispatcher'); lesson(tid, f'задача зависла {idle:.0f} мин', 'LLM/шаг не отвечает', 'при простое шага >N мин: толчок, смена подхода, перезапуск; не ждать молча', 'stall')
            RUNNING.pop(tid, None); sql('UPDATE tasks SET status="queued", restarts=restarts+1 WHERE id=?', (tid,)); STALL[tid] = 0
def inspector():
    """часовой инспектор: движение у активных, уроки записаны и применены, повторов нет"""
    act = sql('SELECT id FROM tasks WHERE status IN ("running","queued")'); stuck = []
    for r in act:
        last = sql('SELECT MAX(ts) m FROM steps WHERE task=?', (r['id'],), one=True)['m'] or 0
        if time.time() - last > 3 * STALL_MIN * 60: stuck.append(r['id'])
    for tid in stuck: step(tid, 'escalate', 'инспектор: нет движения, перезапуск', 'inspector'); sql('UPDATE tasks SET status="queued", restarts=restarts+1 WHERE id=?', (tid,))
    allt = sql('SELECT status FROM tasks'); n = max(len(allt), 1); les = [json.loads(l) for l in open(LESS)] if os.path.exists(LESS) else []
    rep = sum(1 for x in les if x.get('repeat'))
    out = {'ts': int(time.time()), 'active': len(act), 'stuck_restarted': stuck, 'completion_share': round(sum(x['status'] == 'done' for x in allt) / n, 2), 'lessons': len(les), 'repeat_errors': rep,
           'repeat_rate': round(rep / max(len(les), 1), 2), 'lessons_in_brief': len(lessons_text(999).splitlines()), 'nudges': COACH['n']}
    json.dump(out, open(ST + '/inspector.json', 'w'), ensure_ascii=False, indent=1); return out
def _inspector_loop():
    while True:
        time.sleep(3600)
        try: inspector()
        except Exception as e: print('insp err', e, flush=True)

# ---------- бриф Методолога (в промпт КАЖДОГО субисполнителя) + микро-коуч ----------
PB = ST + '/playbooks'
BASE_DEFAULT = ("БРИФ МЕТОДОЛОГА (обязателен):\n1) Сначала фундамент: анализ среды -> готовое из интернета -> оптимизация основы -> функции -> проверка и урок.\n"
 "2) Только готовое, свой код лишь клей.\n3) Собирай и тестируй в песочнице/копии, на прод переноси один раз пакетом; шаги объединяй; долгое запускай в фоне.\n"
 "4) «добавь» не значит «останови/перенеси»: текущее не трогай.\n5) Чистки только по белому списку и с проверкой импортов.\n6) Владельца спрашивай только о деньгах, доступах и удалениях.")
def playbook_kind(t, sub):
    g = (t['goal'] + ' ' + t['title'] + ' ' + sub.get('task', '')).lower()
    if re.search(r'чист|удал|cleanup', g): return 'cleanup'
    if re.search(r'сервер|установ|драйвер|gpu|k1\b', g): return 'server'
    if re.search(r'страниц|сайт|дизайн|лендинг|html', g) or sub.get('role') == 'designer': return 'page'
    return sub.get('role') or 'generic'
def brief(t, sub):
    try: base = open(PB + '/_base.yaml').read()
    except Exception: base = BASE_DEFAULT
    k = playbook_kind(t, sub)
    try: pbk = open(f'{PB}/{k}.yaml').read()
    except Exception: pbk = ''
    cyc = '\nЦИКЛ ДОВЕДЕНИЯ: стопор (что мешает, причина) -> поиск решения (интернет/советники) -> загрузка готового -> внедрение -> замер и улучшение -> следующий стопор, пока нет артефакта. Не зависай молча.'
    ls = lessons_text(); base = base + cyc + ('\nУРОКИ ПРОШЛЫХ ОШИБОК (не повторять):\n' + ls if ls else '')
    return (base.strip() + ('\nПЛЕЙБУК ' + k + ':\n' + pbk.strip() if pbk else ''))[:2500], k
COACH = {'n': 0}
def coach(t, sub, out, names, root, attempt):
    """Сверяет ход с брифом, даёт короткий толчок или ''."""
    g = (t['goal'] + ' ' + sub.get('task', '')).lower(); body = out or ''
    try:
        for f in names:
            fp = os.path.join(root, f)
            if os.path.isfile(fp) and os.path.getsize(fp) < 60000: body += '\n' + open(fp, errors='ignore').read()
    except Exception: pass
    if re.search(r'systemctl (stop|restart|disable)|pkill|kill -9|docker (stop|rm)|shutil\.rmtree|rm -rf', body) and not re.search(r'останов|удал|перезапус|чист', g):
        return 'отклонение: останавливаешь/удаляешь то, о чём не просили. Текущее не трогай; чистка только по белому списку'
    if re.search(r'/workspace/nox/(web|brain)|web_server\.py', body) and re.search(r'open\([^)]*[\'"]w|>\s*/workspace', body):
        return 'отклонение: правка прода напрямую. Собери в песочнице, на прод один пакетом, с бэкапом'
    if re.search(r'уточните|вопрос к владельцу|подтвердите, пожалуйста|как вы хотите', body, re.I) and not re.search(r'деньг|оплат|доступ|ключ|удален', body, re.I):
        return 'отклонение: вопрос владельцу не про деньги/доступ/удаление. Реши сам и запиши допущение'
    if sub.get('role') == 'coder':
        for f in names:
            fp = os.path.join(root, f)
            if f.endswith('.py') and os.path.isfile(fp):
                src = open(fp, errors='ignore').read()
                if src.count('\n') > 150 and not re.search(r'^\s*(import|from)\s+(?!os|sys|re|json|time|math|typing|collections|itertools|functools|pathlib|datetime|unittest|pytest|random|string|hashlib)\w', src, re.M):
                    return 'возьми готовое: >150 строк своего кода без библиотек; найди готовую библиотеку, свой код только клей'
    if attempt >= 1 and len(names) > 3: return 'собери пакетом: объедини шаги в один скрипт/файл'
    return ''

def execute(t, sub, root, feedback='', hint=''):
    r = ROLES().get(sub['role'], ROLES()['writer'])
    ctx = ''
    for f in sorted(os.listdir(root)):
        fp = os.path.join(root, f)
        if os.path.isfile(fp) and not f.startswith('test_') and os.path.getsize(fp) < 6000: ctx += f'\n--- {f} ---\n' + open(fp).read()
    u = f'Задача: {sub["task"]}\nЦель: {t["goal"]}\n' + (f'Уже есть в песочнице:{ctx}\n' if ctx else '') + (f'ЗАМЕЧАНИЯ РЕВИЗОРА (исправь): {feedback}\n' if feedback else '') + (f'ПОДСКАЗКА ТРЕНЕРА: {hint}\n' if hint else '')
    u += '\nОтвет: каждый файл в формате\n### FILE: имя_файла\n<содержимое>\nБез пояснений вне файлов.'
    if NUDGE.get(t['id']): u += 'ТОЛЧОК КОУЧА: ' + NUDGE.pop(t['id']) + '\n'
    bf, bk = brief(t, sub); step(t['id'], 'brief', f'бриф Методолога в промпте ({bk}), {len(bf)} симв.', sub['role'])
    out = llm(r.get('backend', 'main'), r['system'] + '\n\n' + bf, u, r.get('max_tokens', 1800), r.get('temp', 0.3), t['id'])
    names = write_files(root, out); sub['_out'] = out[:6000]
    if not names:        # модель ответила без разметки: сохраняем как текст
        ext = 'html' if sub['role'] in ('designer',) else ('py' if sub['role'] == 'coder' else 'md')
        fn = f'{sub["id"]}.{ext}'; code = re.sub(r'^```[a-zA-Z0-9]*\n|\n```\s*$', '', out.strip())
        open(os.path.join(root, fn), 'w').write(code + '\n'); names = [fn]
    return names

# ---------- ревизор: детерминированная проверка -> судья другой модели ----------
def verify_det(t, sub, root, names):
    role = sub['role']; spec = jload(t.get('spec') or '{}', {}) if isinstance(t.get('spec'), str) else (t.get('spec') or {})
    if spec.get('tests'):
        open(os.path.join(root, 'test_golden.py'), 'w').write(spec['tests']); ok, log = run_pytest(root)
        return ok, 'pytest: ' + log[-600:]
    if role == 'coder':
        py = [n for n in names if n.endswith('.py')]
        if not py: return False, 'нет .py файла'
        if any(n.startswith('test_') for n in py): ok, log = run_pytest(root); return ok, 'pytest: ' + log[-600:]
        r = subprocess.run([sys.executable, '-m', 'py_compile'] + [os.path.join(root, n) for n in py], capture_output=True, text=True)
        return r.returncode == 0, 'py_compile ' + (r.stderr[-300:] or 'ok')
    if role == 'designer':
        hs = [n for n in names if n.endswith('.html')]
        if not hs: return False, 'нет .html'
        p = _H(); txt = open(os.path.join(root, hs[0])).read(); p.feed(txt)
        miss = [x for x in spec.get('html_must', []) if x.lower() not in txt.lower()]
        ok = len(txt) > 600 and 'html' in p.tags and not miss and ('viewport' in txt or not spec.get('html_must'))
        return ok, f'html: {len(txt)}b, тегов {len(p.tags)}, нет: {miss}'
    txt = ''.join(open(os.path.join(root, n)).read() for n in names if os.path.isfile(os.path.join(root, n)))
    miss = [x for x in spec.get('must', []) if x.lower() not in txt.lower()]
    bad = [x for x in spec.get('forbid', []) if x.lower() in txt.lower()]
    wc = len(txt.split()); mx = spec.get('max_words')
    ok = wc >= spec.get('min_words', 20) and not miss and not bad and (not mx or wc <= mx)
    return ok, f'слов {wc}, нет: {miss}, лишнее: {bad}, макс {mx}'
def judge(t, sub, root, names, det_ok, det_log):
    txt = ''
    for n in names:
        fp = os.path.join(root, n)
        if os.path.isfile(fp): txt += f'--- {n} ---\n' + open(fp).read()[:3500]
    rub = 'Ты строгий ревизор. Сверь артефакт с условием готовности. Верни ТОЛЬКО JSON {"score":1-10,"accept":true|false,"reason":"что исправить, кратко"}. Принимай только если score>=7.'
    u = f'Цель: {t["goal"]}\nПодзадача: {sub["task"]}\nАвтопроверка: {"прошла" if det_ok else "НЕ прошла"} ({det_log[-300:]})\n{txt}'
    j = None
    try: j = jparse(llm('judge_llm', rub, u, 300, 0.0, t['id'], 240))
    except Exception as e:
        try: j = jparse(llm('main', rub, u, 300, 0.0, t['id']))
        except Exception as e2: step(t['id'], 'warn', 'судья недоступен: ' + str(e2)[:150])
    if not j: j = {'score': 7 if det_ok else 3, 'accept': det_ok, 'reason': 'судья недоступен, решает автопроверка'}
    try: sc = float(j.get('score', 0))
    except Exception: sc = 0
    j['accept'] = (sc >= 7) and det_ok          # автопроверка имеет право вето
    return j

# ---------- тренер: молчит без триггера ----------
def trainer(t, tries, errs):
    trig = None
    if len(errs) >= 2 and errs[-1][:80] == errs[-2][:80]: trig = 'повтор той же ошибки'
    elif tries >= 2: trig = 'нет прогресса за 2 попытки'
    if not trig: return ''
    step(t['id'], 'trainer', 'триггер: ' + trig)
    try: return llm('trainer', 'Ты тренер. Дай ОДНУ короткую подсказку (до 20 слов): «смени подход», «разбей на части», «достаточно черновика» или «пересоздай с нуля» с причиной.', f'Цель: {t["goal"]}\nОшибки ревизора: {errs[-2:]}', 80, 0.2, t['id'], 120)[:200]
    except Exception: return 'смени подход: перепиши с нуля, учти замечания ревизора'

# ---------- эскалация / консилиум (последовательные волны) ----------
def advisors(): return [a for a in jload(ST + '/advisors_external.json', {}).get('advisors', []) if a.get('status') in ('ok', 'works', 'pass')]
def ext_call(prompt, system='Ты старший советник.'):
    gw = BACK().get('external')
    if not gw: return None
    for a in advisors()[:3]:
        try:
            r = httpx.post(gw['url'].rstrip('/') + '/chat/completions', json={'model': a['provider'] + '/' + a['model'], 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}], 'max_tokens': 900}, timeout=90)
            if r.status_code == 200: return r.json()['choices'][0]['message']['content']
        except Exception: pass
    return None
def consilium(q, rounds=2, budget=170):
    t0 = time.time(); waves = []; angles = [('качество', 'main'), ('скорость и простота', 'judge_llm'), ('риски и слабые места', 'main')]
    cur = ''; best = 0
    for rd in range(rounds):
        for ang, bk in angles:
            if time.time() - t0 > budget: break
            u = f'Вопрос: {q}\n' + (f'Предыдущие версии:\n{cur[-3000:]}\nКритикуй, дополни и дай улучшенную версию.' if cur else 'Дай ответ.') + f'\nРакурс: {ang}.'
            try: out = llm(bk, 'Ты советник консилиума. Отвечай кратко и по делу.', u, 600, 0.4, None, 150)
            except Exception as e: out = None
            if out is None and advisors(): out = ext_call(u)
            if out: waves.append({'angle': ang, 'text': out}); cur += f'\n[{ang}] {out}'
        # стоп-критерий: оценка судьи не растёт
        try:
            sc = float((jparse(llm('judge_llm', 'Оцени полноту и качество ответа, верни JSON {"score":1-10}', cur[-3500:], 60, 0.0, None, 90), {}) or {}).get('score', 0))
        except Exception: sc = 0
        if sc <= best and rd > 0: break
        best = max(best, sc)
    try: final = llm('main', 'Ты старший советник. Своди: согласия, расхождения, итоговое решение. Кратко.', f'Вопрос: {q}\n{cur[-4500:]}', 700, 0.3, None, 200)
    except Exception as e: final = 'старший недоступен: ' + str(e)[:100]
    return {'question': q, 'opinions': waves, 'final': final, 'judge_score': best, 'seconds': round(time.time() - t0), 'external_used': bool(advisors())}

ERR_ADV = []
def _adv_call(a, u, system, mt=500, timeout=70, retry=True):
    gw = BACK().get('external')
    try:
        r = httpx.post(gw['url'].rstrip('/') + '/chat/completions', json={'model': a['provider'] + '/' + a['model'], 'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': u}], 'max_tokens': mt}, timeout=timeout)
        if r.status_code == 200: return (r.json()['choices'][0]['message'].get('content') or '').strip()
        ERR_ADV.append(f'{a.get("model")}: HTTP {r.status_code} {r.text[:80]}')
        if r.status_code in (429, 502) and retry:
            time.sleep(12); return _adv_call(a, u, system, mt, timeout, False)
    except Exception as e: ERR_ADV.append(f'{a.get("model")}: {type(e).__name__}')
    return ''
def consilium_ext(q, deep=False, budget=110):
    """волны: 3 внешних советника параллельно -> (deep) ещё 3 видят первую волну -> старший сводит. Шлюз :8793."""
    t0 = time.time(); adv = [a for a in advisors() if not a.get('role')]; waves = []; seen = ''
    def wave(group, u, name):
        res = []; ths = []
        def one(a): 
            o = _adv_call(a, u, 'Ты советник консилиума. Отвечай кратко (до 120 слов), по делу.')
            if o: res.append({'advisor': a.get('model'), 'text': o[:900]})
        for a in group: th = threading.Thread(target=one, args=(a,)); th.start(); ths.append(th)
        for th in ths: th.join(max(1, budget - (time.time() - t0)))
        waves.append({'wave': name, 'opinions': res}); return res
    w1 = wave(adv[0:3], 'Вопрос: ' + q, 1); seen = '\n'.join(f'[{o["advisor"]}] {o["text"]}' for o in w1)
    if deep and w1 and time.time() - t0 < budget:
        w2 = wave(adv[3:6] or adv[0:3], f'Вопрос: {q}\nМнения первой волны:\n{seen[-2500:]}\nКритикуй и дай улучшенную версию.', 2); seen += '\n' + '\n'.join(f'[{o["advisor"]}] {o["text"]}' for o in w2)
    final = ''; senior = ''
    if seen:
        pref = ['gpt-oss-120b', 'gpt-oss', 'llama-3.3-70b', 'qwen3', 'deepseek', 'nemotron']
        cand = sorted(advisors(), key=lambda a: next((i for i, p in enumerate(pref) if p in a.get('model', '').lower()), 99))
        for a in cand[:3]:     # старший = внешний сильный, пока локальная модель перегружена
            final = _adv_call(a, f'Вопрос: {q}\n{seen[-4500:]}', 'Ты старший советник. Своди мнения: согласия, расхождения, итоговое решение. Кратко.', 600, 60)
            if final: senior = a.get('model'); break
        if not final:
            try: final = llm('main', 'Ты старший советник. Своди мнения: согласия, расхождения, итоговое решение. Кратко.', f'Вопрос: {q}\n{seen[-4500:]}', 600, 0.3, None, 100); senior = 'local main'
            except Exception: final = 'старший недоступен; см. мнения волн'
    else: final = 'внешние советники не ответили'
    return {'question': q, 'deep': deep, 'waves': waves, 'final': final, 'senior': senior, 'seconds': round(time.time() - t0), 'advisors_available': len(adv), 'errors': ERR_ADV[-3:]}

# ---------- supervisor-граф по задаче ----------
def run_task(tid):
    t = dict(sql('SELECT * FROM tasks WHERE id=?', (tid,), one=True))
    root = os.path.join(SB, tid); os.makedirs(root, exist_ok=True)
    sql('UPDATE tasks SET status="running", started=COALESCE(started,?), hb=? WHERE id=?', (time.time(), time.time(), tid))
    pl = jload(t['plan'] or '', None) or plan(t)
    sql('UPDATE tasks SET plan=? WHERE id=?', (json.dumps(pl, ensure_ascii=False), tid)); step(tid, 'plan', json.dumps(pl, ensure_ascii=False)[:1500])
    results = []; escal = False; total_returns = 0; first_pass = 1
    done = set(); subs = pl['subtasks']
    while len(done) < len(subs):
        ready = [s for s in subs if s['id'] not in done and all(d in done for d in s.get('deps', []))] or [s for s in subs if s['id'] not in done][:1]
        ths = []
        def work(sub):
            nonlocal total_returns, first_pass, escal
            fb = ''; hint = ''; errs = []; names = []; verdict = None; coached = False
            for attempt in range(4):          # 1 + максимум 2 возврата
                step(tid, 'exec', f'{sub["role"]} попытка {attempt + 1}', sub['role'])
                try: names = execute(t, sub, root, fb, hint)
                except Exception as e: errs.append('exec: ' + str(e)[:200]); fb = errs[-1]; names = []; hint = trainer(t, attempt + 1, errs); continue
                if not coached:
                    ch = coach(t, sub, sub.get('_out', ''), names, root, attempt)
                    if ch: coached = True; COACH['n'] += 1; step(tid, 'coach', ch, 'coach'); lesson(tid, 'отклонение от брифа: ' + sub.get('task', '')[:80], 'коуч', ch.split(':', 1)[-1].strip(), 'coach'); hint = ch; fb = 'коуч: ' + ch; continue
                ok, log = verify_det(t, sub, root, names)
                v = judge(t, sub, root, names, ok, log); step(tid, 'review', f'{"ПРИНЯТО" if v["accept"] else "ВОЗВРАТ"} score={v.get("score")} {log[-200:]} | {v.get("reason", "")}', 'reviewer')
                if v['accept']: verdict = v; break
                step(tid, 'stopper', 'стопор: ' + (v.get('reason', '') + ' | ' + log)[-250:], 'reviewer'); lesson(tid, 'возврат ревизора: ' + sub['task'][:60], (v.get('reason', '') + ' ' + log)[-150:], 'до сдачи проверь: ' + (v.get('reason', '') or log)[:120], 'review')
                if attempt >= 1 and advisors():
                    try: hint = (hint + ' СОВЕТНИК: ' + ext_call('Как решить стопор: ' + (v.get('reason', '') + ' ' + log)[-300:] + ' Ответь 2 предложениями.')[:300]).strip(); step(tid, 'search', 'решение у советников: ' + hint[-150:], 'advisor')
                    except Exception: pass
                total_returns += 1; first_pass = 0; fb = (v.get('reason', '') + ' | ' + log)[-700:]; errs.append(fb)
                hint = trainer(t, attempt + 1, errs)
            if not verdict:
                escal = True; step(tid, 'escalate', f'{sub["id"]}: возвраты исчерпаны', 'reviewer'); lesson(tid, f'подзадача {sub["id"]} не принята', fb[:150], 'при 2 возвратах: смени подход и возьми готовое сразу', 'escalate')
                out = ext_call(f'Задача: {sub["task"]}\nЗамечания: {fb}\nДай исправленный результат файлами в формате ### FILE: имя') if advisors() else None
                if out and write_files(root, out):
                    ok, log = verify_det(t, sub, root, names); verdict = {'accept': ok, 'reason': 'внешний советник: ' + log[-100:]}
                    step(tid, 'escalate', 'внешний советник: ' + ('принято автопроверкой' if ok else 'не помогло'), 'advisor')
            results.append({'sub': sub['id'], 'role': sub['role'], 'files': names, 'accepted': bool(verdict and verdict.get('accept')), 'note': (verdict or {}).get('reason', fb)[:300]})
        for s in ready: th = threading.Thread(target=work, args=(s,)); th.start(); ths.append(th)
        for th in ths: th.join()
        for s in ready: done.add(s['id'])
    ok = all(r['accepted'] for r in results)
    arts = [{'path': f'{tid}/{f}', 'url': f'/svc/agents/artifact/{tid}/{f}'} for r in results for f in r['files']]
    card = {'done': [r for r in results if r['accepted']], 'failed': [r for r in results if not r['accepted']], 'artifacts': arts, 'goal': pl.get('goal'), 'actions': ['Принять', 'Доработать', 'Откатить']}
    now = time.time(); t0_ = sql('SELECT started FROM tasks WHERE id=?', (tid,), one=True)['started'] or now; rc = {'task': tid, 'title': t['title'], 'goal': pl.get('goal'), 'done': [{'sub': r['sub'], 'role': r['role'], 'accepted': r['accepted'], 'note': r['note'][:120]} for r in results],
          'artifacts': [], 'started': t0_, 'finished': now, 'seconds': round(now - t0_), 'returns': total_returns,
          'fallbacks': sql('SELECT count(*) c FROM steps WHERE task=? AND kind="fallback"', (tid,), one=True)['c'], 'accepted': ok}
    for a in arts:
        fp = os.path.join(SB, a['path'])
        try: rc['artifacts'].append({'path': a['path'], 'bytes': os.path.getsize(fp), 'sha256': hashlib.sha256(open(fp, 'rb').read()).hexdigest()})
        except Exception: pass
    card['receipt'] = rc
    try: json.dump(rc, open(os.path.join(root, 'receipt.json'), 'w'), ensure_ascii=False, indent=1)
    except Exception: pass
    sql('UPDATE tasks SET status=?, finished=?, result=?, first_pass=?, returns=? WHERE id=? AND status!="cancelled"', ('done' if ok else 'needs_owner', time.time(), json.dumps(card, ensure_ascii=False), first_pass if ok else 0, total_returns, tid))
    step(tid, 'final', 'готово' if ok else 'не всё получилось, нужен владелец')

# ---------- диспетчер-1 (lease, очередь, heartbeat) ----------
QUEUE_WORKERS = int(os.environ.get('NOX_AG_WORKERS', '10')); RUNNING = {}
OWNER = f'disp1-{os.getpid()}'
def lease_beat():
    sql('INSERT INTO lease(k,owner,ts) VALUES("disp1",?,?) ON CONFLICT(k) DO UPDATE SET owner=?, ts=?', (OWNER, time.time(), OWNER, time.time()))
    jdump = {'running': len(RUNNING), 'queued': sql('SELECT count(*) c FROM tasks WHERE status="queued"', one=True)['c'], 'active': len(RUNNING) > 0, 'inflight': len(RUNNING), 'ts': int(time.time())}
    json.dump(jdump, open(ST + '/agents_activity.json.tmp', 'w')); os.replace(ST + '/agents_activity.json.tmp', ST + '/agents_activity.json')
def dispatcher():
    while True:
        try:
            lease_beat(); stall_check()
            if time.time() - (os.path.getmtime(ST + '/agents_guard.hb') if os.path.exists(ST + '/agents_guard.hb') else 0) > 60:   # взаимный перезапуск: диспетчер-1 поднимает стража
                subprocess.Popen(['setsid', 'nohup', sys.executable, A + '/agents_guard.py'], stdin=subprocess.DEVNULL, stdout=open(A + '/guard.log', 'a'), stderr=subprocess.STDOUT, start_new_session=True)
                open(ST + '/agents_guard.hb', 'a').close(); os.utime(ST + '/agents_guard.hb')
            for tid, th in list(RUNNING.items()):
                if not th.is_alive(): RUNNING.pop(tid)
            for tid2, th2 in list(RUNNING.items()):
                if th2.is_alive(): sql('UPDATE tasks SET hb=? WHERE id=?', (time.time(), tid2))     # heartbeat живого исполнителя
            for r in sql('SELECT id,hb FROM tasks WHERE status="running"'):      # осиротевшие (нет потока, напр. после рестарта сервиса)
                if r['id'] not in RUNNING and time.time() - (r['hb'] or 0) > 20:
                    sql('UPDATE tasks SET status="queued", restarts=restarts+1 WHERE id=?', (r['id'],)); step(r['id'], 'requeue', f'сирота: нет потока в pid {os.getpid()}, hb {time.time() - (r["hb"] or 0):.0f} с назад', 'dispatcher')
            while True:
                r = sql('SELECT id,prio FROM tasks WHERE status="queued" ORDER BY prio DESC, created LIMIT 1', one=True)
                if not r: break
                if len(RUNNING) >= QUEUE_WORKERS + (3 if (r['prio'] or 0) >= 10 else 0): break
                sql('UPDATE tasks SET status="running", hb=? WHERE id=?', (time.time(), r['id']))
                th = threading.Thread(target=lambda i=r['id']: _safe(i), daemon=True); RUNNING[r['id']] = th; th.start()
        except Exception as e: print('disp err', e, flush=True)
        time.sleep(3)
def _safe(i):
    try: run_task(i)
    except Exception as e:
        step(i, 'error', repr(e)[:400]); sql('UPDATE tasks SET status="failed", finished=? WHERE id=?', (time.time(), i))

def new_task(title, goal, role=None, team=None, project='', spec=None, prio=None):
    if prio is None: prio = 10 if project == 'chat' else -5 if project == 'golden' else -1 if re.match(r'(worm|idea|self)', project or '') else 0
    tid = time.strftime('%m%d') + '-' + uuid.uuid4().hex[:6]
    sql('INSERT INTO tasks(id,title,goal,role,team,project,status,created,spec,prio) VALUES(?,?,?,?,?,?,"queued",?,?,?)', (tid, title, goal, role, team, project, time.time(), json.dumps(spec or {}, ensure_ascii=False), prio))
    return tid

def metrics():
    r = sql('SELECT * FROM tasks'); done = [x for x in r if x['status'] == 'done']
    hrs = max((time.time() - min([x['created'] for x in r] or [time.time()])) / 3600, 0.01)
    return {'total': len(r), 'done': len(done), 'needs_owner': sum(x['status'] == 'needs_owner' for x in r), 'failed': sum(x['status'] == 'failed' for x in r),
            'closed_with_artifact_per_hour': round(len(done) / hrs, 2), 'first_pass_share': round(sum(x['first_pass'] or 0 for x in done) / max(len(done), 1), 2),
            'avg_seconds': round(sum((x['finished'] or 0) - (x['started'] or 0) for x in done) / max(len(done), 1), 1), 'restarts': sum(x['restarts'] or 0 for x in r), 'coach_nudges': COACH['n'], 'lessons': REPEAT['lessons'], 'repeat_errors': REPEAT['n'], 'tokens': sum(x['tokens'] or 0 for x in r)}

# ---------- HTTP ----------
app = FastAPI()
def strip(p):  # убираем префикс /svc/agents на случай прокси
    return p
@app.get('/health')
def health(): return {'ok': True, 'owner': OWNER, **jload(ST + '/agents_activity.json', {})}
@app.get('/')
def root():
    return {'service': 'agents', 'running': len(RUNNING), 'inflight': len(RUNNING), 'active': len(RUNNING) > 0, 'queued': sql('SELECT count(*) c FROM tasks WHERE status="queued"', one=True)['c'], 'metrics': metrics()}
@app.post('/task')
async def post_task(req: Request):
    b = await req.json()
    if b.get('dangerous'): return JSONResponse({'error': 'опасные операции только с подтверждением владельца'}, 403)
    tid = new_task(b.get('title') or (b.get('goal', '')[:60]), b['goal'], b.get('role'), b.get('team'), ('chat' if b.get('source') == 'chat' else b.get('project', '')), b.get('spec'))
    return {'id': tid, 'status': 'queued'}
@app.get('/task/{tid}')
def get_task(tid: str):
    r = sql('SELECT * FROM tasks WHERE id=?', (tid,), one=True)
    if not r: return JSONResponse({'error': 'нет такой'}, 404)
    d = dict(r); d['plan'] = jload(d['plan'] or '', None) if d['plan'] and not isinstance(d['plan'], dict) else d['plan']
    d['result'] = json.loads(d['result']) if d['result'] else None; d.pop('spec', None)
    d['steps'] = [dict(s) for s in sql('SELECT ts,kind,role,text FROM steps WHERE task=? ORDER BY id', (tid,))]
    return d
@app.get('/task/{tid}/receipt')
def get_receipt(tid: str):
    r = sql('SELECT result FROM tasks WHERE id=?', (tid,), one=True)
    rc = (json.loads(r['result']) if r and r['result'] else {}).get('receipt')
    return rc or JSONResponse({'error': 'квитанции нет (задача не завершена)'}, 404)
@app.get('/task/{tid}/card')
def get_card(tid: str): return card(tid) or JSONResponse({'error': 'нет'}, 404)
@app.get('/board')
def board():
    cols = {'Нужен ты': [], 'В работе': [], 'Очередь': [], 'Готово': [], 'Отменено': []}
    for r in sql('SELECT id FROM tasks ORDER BY created DESC LIMIT 60'):
        c = card(r['id']); cols[c['column']].append(c)
    return cols
@app.get('/inspect')
def inspect_now(): return inspector()
@app.get('/lessons')
def get_lessons(): return [json.loads(l) for l in open(LESS)][-50:] if os.path.exists(LESS) else []
@app.post('/task/{tid}/cancel')
def cancel(tid: str):
    sql('UPDATE tasks SET status="cancelled", finished=? WHERE id=? AND status IN ("queued","running")', (time.time(), tid)); lesson(tid, 'задача отменена (дубль/зависшая)', 'владелец/диспетчер', 'перед запуском пакета проверять дубли по title+goal', 'cancel'); return {'ok': True}
@app.get('/tasks')
def tasks(): return [dict(r) for r in sql('SELECT id,title,status,role,team,created,finished,returns,restarts FROM tasks ORDER BY created DESC LIMIT 100')]
def make_team(preset, goal, title=None, project=''):
    pr = TEAMS().get(preset)
    if not pr: return None
    return [new_task(f'{title or preset}: {m["role"]}', (m.get('task') or '') + ' ' + goal, m['role'], preset, project) for m in pr['members']]
@app.post('/team')
async def post_team(req: Request):
    b = await req.json(); ids = make_team(b['preset'], b.get('goal', ''), b.get('title'), b.get('project', ''))
    if ids is None: return JSONResponse({'error': 'нет пресета', 'presets': list(TEAMS())}, 404)
    return {'preset': b['preset'], 'ids': ids}
@app.get('/teams')
def teams(): return TEAMS()
@app.post('/consilium')
async def post_consilium(req: Request):
    b = await req.json()
    if b.get('mode', 'ext') == 'ext': return await asyncio.to_thread(consilium_ext, b['question'], bool(b.get('deep')), int(b.get('budget', 110)))
    return await asyncio.to_thread(consilium, b['question'], int(b.get('rounds', 2)), int(b.get('budget', 170)))
@app.post('/command')
async def command(req: Request):      # чат-команда /команда <цель> [--team пресет]
    b = await req.json(); txt = b.get('text', '').strip(); m = re.match(r'^/(команда|team)\s*(\S+)?\s*(.*)$', txt, re.S)
    if not m: return JSONResponse({'error': 'формат: /команда <пресет> <цель>'}, 400)
    pre, goal = m.group(2) or 'dev2', m.group(3)
    ids = make_team(pre, goal, project='chat')
    return {'preset': pre, 'ids': ids} if ids else JSONResponse({'error': 'нет пресета', 'presets': list(TEAMS())}, 404)
@app.post('/correction')
async def post_corr(req: Request):
    b = await req.json(); save_correction(b['said'], b.get('understood', ''), b['wanted']); return {'ok': True}
@app.get('/intents/eval')
def intents_eval():
    g = jload(A + '/golden_intents.json', []); res = []
    for c in g:
        p = passport(c['phrase'], fast=True); ok = (p['verb'] == c['verb'] or c['verb'] in p['verbs']) and (p['stop_current'] == c.get('stop_current', False))
        res.append({'phrase': c['phrase'][:80], 'got': p['verb'], 'stop_current': p['stop_current'], 'ok': ok})
    return {'n': len(res), 'ok': sum(r['ok'] for r in res), 'share': round(sum(r['ok'] for r in res) / max(len(res), 1), 2), 'cases': res}
@app.get('/metrics')
def get_metrics(): return metrics()
@app.get('/events')
def events():
    def gen():
        while True:
            try: yield 'data: ' + json.dumps(EV.get(timeout=15), ensure_ascii=False) + '\n\n'
            except queue.Empty: yield ': ping\n\n'
    return StreamingResponse(gen(), media_type='text/event-stream')
@app.get('/artifact/{tid}/{path:path}')
def artifact(tid: str, path: str):
    from fastapi.responses import FileResponse
    try: p = safe_path(os.path.join(SB, tid), path)
    except ValueError: return JSONResponse({'error': 'путь'}, 400)
    return FileResponse(p) if os.path.isfile(p) else JSONResponse({'error': 'нет файла'}, 404)
@app.post('/golden')
async def golden(req: Request):
    g = jload(A + '/golden.json', []); ids = []
    for x in g: ids.append(new_task(x['title'], x['goal'], x['role'], None, 'golden', x.get('spec')))
    return {'ids': ids}
@app.get('/golden/result')
def golden_result():
    rs = [dict(r) for r in sql('SELECT id,title,role,status,first_pass,returns,started,finished FROM tasks WHERE project="golden" ORDER BY created DESC LIMIT 10')]
    acc = sum(r['status'] == 'done' for r in rs); return {'n': len(rs), 'accepted': acc, 'share': round(acc / max(len(rs), 1), 2), 'tasks': rs}

@app.on_event('startup')
def _start():
    threading.Thread(target=dispatcher, daemon=True).start(); threading.Thread(target=_inspector_loop, daemon=True).start()
    try:
        sys.path.insert(0, A); import nox_worms
        nox_worms.mount(app, lambda b, s, u, mt=600, tp=0.3, tid=None, to=300: llm(b, s, u, mt, tp, tid, to), chat_busy, lambda x, a=(): sql(x, a), new_task, lambda: len(RUNNING))
    except Exception as e: print('worms mount fail', e, flush=True)
if __name__ == '__main__':
    import uvicorn; uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')
