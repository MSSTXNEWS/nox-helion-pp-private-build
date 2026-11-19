"""V112 native WEB V29.3: owner-authenticated chat, S03 dialogs, and isolated UI.

Drop-in replacement for existing nox_v29_chat_bridge.py loaded by V108.
No second LLM, no extra SQLite file, no new scheduler, no mock 'done'.
The one existing S03 database retains all original tables and content.
"""
from __future__ import annotations

import asyncio
import codecs
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid
import urllib.request
from typing import Mapping

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

SITE = Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site')
ID_PATTERN = re.compile(r'^[a-f0-9]{32}$')
OWNER = 'nox-single-owner'
SCHEMA = """
CREATE TABLE IF NOT EXISTS nox_v29_dialogs (
 dialog_id TEXT PRIMARY KEY, owner TEXT NOT NULL,
 title TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS nox_v29_dialog_owner_time
 ON nox_v29_dialogs(owner,archived,updated_at DESC);
CREATE TABLE IF NOT EXISTS nox_v29_dialog_messages (
 row_id INTEGER PRIMARY KEY AUTOINCREMENT,
 dialog_id TEXT NOT NULL REFERENCES nox_v29_dialogs(dialog_id),
 exchange_id TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')),
 content TEXT NOT NULL, ts TEXT NOT NULL,
 UNIQUE(dialog_id,exchange_id,role)
);
CREATE INDEX IF NOT EXISTS nox_v29_messages_order
 ON nox_v29_dialog_messages(dialog_id,row_id);
"""

@contextmanager
def _db(write=False):
    """Preserve SQLite transaction semantics and CLOSE every original S03 handle.

    sqlite3.Connection.__exit__ only commits/rolls back; it never closes.
    Owner WEB chat/status/history routes use this existing context repeatedly.
    """
    import s03_memory
    path = Path(s03_memory.DB)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError('HOLD_EXISTING_S03_FILE')
    target = 'file:' + str(path) + ('?mode=rw' if write else '?mode=ro')
    conn = sqlite3.connect(target, uri=True, timeout=4)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout=4000')
        conn.execute('PRAGMA foreign_keys=ON')
        with conn:
            yield conn
    finally:
        conn.close()

def ensure_dialog_schema():
    """Add only two tables and indexes inside preexisting S03 SQLite (no new DB)."""
    with _db(True) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='s03_items'").fetchone() is None:
            raise RuntimeError('HOLD_ORIGINAL_S03_SCHEMA')
        db.executescript(SCHEMA)
    return _schema_ready()

def _schema_ready():
    try:
        with _db() as db:
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        return {'s03_items','nox_v29_dialogs','nox_v29_dialog_messages'} <= tables
    except (OSError, RuntimeError, sqlite3.Error, ImportError, ValueError):
        return False

def _s03_ready():
    try:
        with _db() as db:
            return db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='s03_items'").fetchone() is not None
    except (OSError, RuntimeError, sqlite3.Error, ImportError, ValueError):
        return False

def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')

def _row(row):
    return {'dialog_id':row['dialog_id'], 'title':row['title'],
            'archived':bool(row['archived']), 'revision':row['revision'],
            'updated':row['updated_at'], 'created':row['created_at']}

def _get_dialog(db, dialog_id):
    if not isinstance(dialog_id,str) or not ID_PATTERN.fullmatch(dialog_id):
        return None
    return db.execute(
        'SELECT * FROM nox_v29_dialogs WHERE owner=? AND dialog_id=?',
        (OWNER, dialog_id)).fetchone()

def _jsonl(obj: Mapping):
    return json.dumps(obj, ensure_ascii=False, separators=(',',':')) + '\n'

def _sse_delta(line):
    if not line.startswith('data:'):
        return '', ''
    wire = line[5:].strip()
    if wire == '[DONE]':
        return 'done', ''
    try:
        obj = json.loads(wire)
        if not isinstance(obj,dict):
            return 'malformed', ''
        # An upstream inference error is not a harmless empty delta. Never
        # permit a later [DONE] plus unrelated S03 proof to claim success.
        if 'error' in obj and obj['error'] is not None:
            return 'upstream_error', ''
        # Usage-only chunks are valid; malformed choices must invalidate
        # previous output even if the upstream later sends [DONE].
        if 'choices' not in obj and isinstance(obj.get('usage'),dict):
            return '', ''
        choices=obj.get('choices')
        # A single Resonance reply is bound to one S03 exchange. Returning
        # the first delta before checking sibling choices could hide a later
        # truncated/error choice in the SAME upstream SSE frame.
        if not isinstance(choices,list) or len(choices)>1:
            return 'malformed', ''
        for row in choices:
            if not isinstance(row,dict):
                return 'malformed', ''
            # A terminal finish_reason other than stop means incomplete or
            # unsupported generation. A later [DONE] plus matching S03 proof
            # cannot convert truncated/filter-blocked text into success.
            finish_reason = row.get('finish_reason')
            if finish_reason is not None and finish_reason != 'stop':
                return 'upstream_finish_incomplete', ''
            delta = row.get('delta')
            if delta is not None and not isinstance(delta,dict):
                return 'malformed', ''
            if isinstance(delta,dict):
                content=delta.get('content')
                if content is not None and not isinstance(content,str):
                    return 'malformed', ''
                if content:
                    return 'delta',content
    except (TypeError,ValueError):
        # Broken upstream data is a protocol error, not an ignorable token.
        return 'malformed', ''
    return '', ''

def _timestamp(value):
    try:
        if isinstance(value,(int,float)) or str(value).replace('.','',1).isdigit():
            return float(value)
        d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return d.replace(tzinfo=timezone.utc).timestamp() if d.tzinfo is None else d.timestamp()
    except (TypeError,ValueError,OverflowError):
        return float('-inf')

def _readback(question,answer,started_at):
    """A new committed S03 record is required; old matching rows are invalid."""
    if len(question.strip())<1 or len(answer.strip())<2:
        return None
    try:
        with _db() as db:
            rows = db.execute(
                'SELECT id,sha256,ts FROM s03_items '
                'WHERE instr(text,?)>0 AND instr(text,?)>0 '
                'ORDER BY ts DESC LIMIT 15',
                (question[:160],answer[:150])
            ).fetchall()
        for row in rows:
            if (_timestamp(row['ts'])+2 < started_at or
                not isinstance(row['id'],str) or len(row['id'])<6 or
                not isinstance(row['sha256'],str) or
                not re.fullmatch('[a-fA-F0-9]{64}',row['sha256'])):
                continue
            return {'record_id':row['id'],'sha256':row['sha256']}
    except (OSError,sqlite3.Error,RuntimeError,ImportError,ValueError):
        pass
    return None

def _save_exchange(dialog_id,question,answer,exchange_id):
    if not dialog_id:
        return True
    stamp=_now()
    try:
        with _db(True) as db:
            row=_get_dialog(db,dialog_id)
            if row is None or bool(row['archived']):
                return False
            # A durable S03 exchange_id must never certify DIFFERENT dialog
            # text. INSERT OR IGNORE + COUNT(*)=2 accepted a stale collision.
            expected={'user':question,'assistant':answer}
            existing=db.execute(
                'SELECT role,content FROM nox_v29_dialog_messages '
                'WHERE dialog_id=? AND exchange_id=?',
                (dialog_id,exchange_id)).fetchall()
            if existing:
                observed={r['role']:r['content'] for r in existing}
                if len(existing)!=2 or observed!=expected:
                    raise RuntimeError('HOLD_DIALOG_RECEIPT_COLLISION')
                # Exact replay: already persisted; do not fabricate a new
                # revision or overwrite the original durable exchange.
                return True
            for role,content in expected.items():
                db.execute(
                    'INSERT INTO nox_v29_dialog_messages '
                    '(dialog_id,exchange_id,role,content,ts) VALUES(?,?,?,?,?)',
                    (dialog_id,exchange_id,role,content,stamp))
            saved=db.execute(
                'SELECT role,content FROM nox_v29_dialog_messages '
                'WHERE dialog_id=? AND exchange_id=?',
                (dialog_id,exchange_id)).fetchall()
            if len(saved)!=2 or {r['role']:r['content'] for r in saved}!=expected:
                raise RuntimeError('HOLD_DIALOG_RECEIPT_CONTENT')
            db.execute('UPDATE nox_v29_dialogs SET updated_at=?,revision=revision+1 '
                       'WHERE owner=? AND dialog_id=?',(stamp,OWNER,dialog_id))
        return True
    except (OSError,sqlite3.Error,RuntimeError,ImportError,ValueError):
        return False

def _validated_history(data):
    history=data['history'] if 'history' in data else []
    if not isinstance(history,list) or len(history)>24:
        raise ValueError('HOLD_HISTORY_LIMIT')
    clean=[];size=0
    for row in history:
        if not isinstance(row,dict) or row.get('role') not in ('user','assistant'):
            raise ValueError('HOLD_HISTORY_ROLE')
        content=row.get('content')
        if not isinstance(content,str) or len(content)>8000:
            raise ValueError('HOLD_HISTORY_CONTENT')
        size+=len(content.encode('utf-8'))
        if size>121000:
            raise ValueError('HOLD_HISTORY_SIZE')
        clean.append({'role':row['role'],'content':content})
    return clean

def _dialog_context(dialog_id):
    """Load complete authorized committed pairs or HOLD; never clip dialog memory.

    The legacy context budget is 24 messages / 121 KB / 8,000 characters per
    message. If the stored thread exceeds it, return HOLD before inference
    instead of silently selecting recent turns or truncating message text.
    """
    with _db() as db:
        found=_get_dialog(db,dialog_id)
        if found is None:
            return 'HOLD_DIALOG_SCOPE_NOT_BOUND',[]
        if bool(found['archived']):
            return 'HOLD_DIALOG_ARCHIVED',[]
        stats=db.execute(
            'SELECT COUNT(*), '
            'COALESCE(SUM(length(CAST(content AS BLOB))),0), '
            'COALESCE(MAX(length(content)),0) '
            'FROM nox_v29_dialog_messages WHERE dialog_id=?',
            (dialog_id,)).fetchone()
        message_count,total_bytes,max_chars=stats[0],stats[1],stats[2]
        if message_count>24:
            return 'HOLD_HISTORY_LIMIT',[]
        if max_chars>8000:
            return 'HOLD_HISTORY_CONTENT',[]
        if total_bytes>121000:
            return 'HOLD_HISTORY_SIZE',[]
        invalid_pair=db.execute(
            'SELECT 1 FROM nox_v29_dialog_messages WHERE dialog_id=? '
            'GROUP BY exchange_id HAVING COUNT(*)!=2 OR '
            'SUM(CASE WHEN role=\'user\' THEN 1 ELSE 0 END)!=1 OR '
            'SUM(CASE WHEN role=\'assistant\' THEN 1 ELSE 0 END)!=1 LIMIT 1',
            (dialog_id,)).fetchone()
        if invalid_pair is not None:
            return 'HOLD_HISTORY_PAIR_INCOMPLETE',[]
        rows=db.execute(
            'SELECT u.content AS question, a.content AS answer '
            'FROM nox_v29_dialog_messages AS a '
            'JOIN nox_v29_dialog_messages AS u '
            'ON u.dialog_id=a.dialog_id AND u.exchange_id=a.exchange_id '
            "AND u.role='user' WHERE a.dialog_id=? AND a.role='assistant' "
            'ORDER BY a.row_id DESC',(dialog_id,)).fetchall()
    pairs=[];size=0
    for row in rows:
        question,answer=row['question'],row['answer']
        if not isinstance(question,str) or not isinstance(answer,str):
            raise RuntimeError('HOLD_S03_DIALOG_CONTEXT_CONTENT')
        if len(question)>8000 or len(answer)>8000:
            return 'HOLD_HISTORY_CONTENT',[]
        pair_size=len(question.encode('utf-8'))+len(answer.encode('utf-8'))
        if size+pair_size>121000:
            return 'HOLD_HISTORY_SIZE',[]
        size+=pair_size
        pairs.append([{'role':'user','content':question},
                      {'role':'assistant','content':answer}])
    return None,[message for pair in reversed(pairs) for message in pair]

def _model_name(data):
    candidate = data.get('model')
    if isinstance(candidate,str):
        return candidate[:200]
    if isinstance(candidate,dict):
        for key in ('name','model','id'):
            value=candidate.get(key)
            if isinstance(value,str) and value:
                return value[:200]
    return ''

_FROZEN_V29_CATALOG_SHA = 'c509870d8fc664bb7c60cd53d3daf21280aa410832d978d3fedbd0543730f661'
_ORIGINAL_CATALOG_LINK = "const path=page=>native?'/nox/'+page:(files[page]||page)+'.html';"
_STAGED_CATALOG_LINK = (
    "const path=page=>native&&location.pathname.startsWith('/nox-web-v29/')?"
    "'/nox-web-v29/'+(files[page]||page)+'.html':"
    "native?'/nox/'+page:(files[page]||page)+'.html';"
)


def _catalog_owner_overlay(raw: bytes, expected_sha: str = _FROZEN_V29_CATALOG_SHA) -> bytes:
    """Fix only frozen catalog navigation in the existing authenticated WEB mount.

    Neither changes the frozen ZIP/on-disk source nor affects Windows native
    /nox/* routes. No new backend and no synthetic command execution.
    """
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('HOLD_FROZEN_V29_CATALOG_SHA')
    text = raw.decode('utf-8')
    if text.count(_ORIGINAL_CATALOG_LINK) != 1:
        raise ValueError('HOLD_CATALOG_LINK_SOURCE_DRIFT')
    return text.replace(_ORIGINAL_CATALOG_LINK, _STAGED_CATALOG_LINK, 1).encode('utf-8')



_V122_FROZEN_NOX_UI_SHA = 'c5f6b23d5fc6c31c4c388a574bfa8c61243cda6000cefb0026732ebe4183b765'
_V122_OWNER_UI_PATCHES = (
    (
        "const sampledAt=number(observedActivity?.sampled_at),age=sampledAt===null?null:Date.now()/1000-sampledAt;",
        "const sampledAt=number(observedActivity?.sampled_at??observedActivity?.timestamp),age=sampledAt===null?null:Date.now()/1000-sampledAt;",
    ),
    (
        "const observedKnown=observedActivity?.status==='OBSERVED_NATIVE_OWNER'&&Number.isInteger(count)&&count>=0&&age!==null&&age>=-5&&age<=30;",
        "const observedKnown=(observedActivity?.status==='OBSERVED_NATIVE_OWNER'||(observedActivity?.status==='READY'&&observedActivity?.source==='ACTUAL_NOX_MODEL_SLOTS'))&&Number.isInteger(count)&&count>=0&&age!==null&&age>=-5&&age<=30;",
    ),
    (
        "const ready=health?.status==='READY'&&health.owner_transport_bound===true&&core?.native_p02_bound===true&&core.native_contract?.transport_bound===true&&typeof core.primary_model==='string'&&Boolean(core.primary_model);",
        "const ready=health?.status==='READY'&&health?.backend==='EXISTING_NOX_ONEHOST'&&health.chat_http===200&&health.model_http===200&&core?.backend==='EXISTING_NATIVE_ONEHOST'&&core.native_p02_bound===true&&core.native_cognitive_memory_bound===true&&core.native_dialogs_ready===true&&typeof core.primary_model==='string'&&Boolean(core.primary_model);",
    ),
)


def _overlay_v122_owner_ui(raw: bytes, *, expected_sha: str = _V122_FROZEN_NOX_UI_SHA) -> bytes:
    """Keep frozen V29.3 bytes untouched. Reconcile owner-proven V118 HTTP fields.

    No fabricated health, inference activity or GPU figures: all ready fields
    require real authenticated OneHost, live model HTTP and durable S03.
    Only served inside the already-protected /nox-web-v29/ mount.
    """
    if not isinstance(raw,bytes) or len(raw)>100_000:
        raise ValueError('HOLD_V122_OWNER_UI_INPUT')
    if hashlib.sha256(raw).hexdigest()!=expected_sha:
        raise ValueError('HOLD_V122_FROZEN_NOX_UI_SHA')
    try:
        source=raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ValueError('HOLD_V122_OWNER_UI_ENCODING') from exc
    for old,new in _V122_OWNER_UI_PATCHES:
        if source.count(old)!=1 or new in source:
            raise ValueError('HOLD_V122_OWNER_UI_ANCHOR_DRIFT')
        source=source.replace(old,new,1)
    return source.encode('utf-8')


async def _next_native_chunk_or_stop(iterator, cancel: asyncio.Event):
    """Race the next real model token against scoped STOP, with no busy-wait.

    Stops the *HTTP stream* even when the upstream model has not emitted its
    next token. This is NOT proof that GPU compute has ceased: that requires
    a native model slot receipt. No S03 write occurs in this helper.
    """
    if cancel.is_set():
        return ('stop', None)
    next_task = asyncio.create_task(anext(iterator))
    stop_task = asyncio.create_task(cancel.wait())
    try:
        finished, _ = await asyncio.wait(
            {next_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
        if stop_task in finished or cancel.is_set():
            next_task.cancel()
            try:
                await asyncio.wait_for(next_task, timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError,
                    StopAsyncIteration):
                pass
            return ('stop', None)
        try:
            return ('chunk', await next_task)
        except StopAsyncIteration:
            return ('eof', None)
    finally:
        # Browser disconnects cancel this coroutine directly, without setting
        # the scoped STOP event. Drain its outstanding anext() as well, or the
        # caller cannot aclose() the still-running native stream.
        next_task.cancel()
        stop_task.cancel()
        await asyncio.gather(next_task, stop_task, return_exceptions=True)


class _OwnerStatic(StaticFiles):
    def __init__(self, directory, auth, unauthorized):
        super().__init__(directory=str(directory), html=True, check_dir=True)
        self._auth=auth
        self._unauthorized=unauthorized

    async def __call__(self,scope,receive,send):
        if scope.get('type')=='http' and not self._auth(Request(scope,receive)):
            await self._unauthorized()(scope,receive,send)
            return
        await super().__call__(scope,receive,send)

    async def get_response(self,path,scope):
        if path.lstrip('/')=='native-owner.js':
            return Response('window.NOX_NATIVE_OWNER = true;',
                            media_type='application/javascript',
                            headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
        response=await super().get_response(path,scope)
        if path.lstrip('/')=='nox-ui.js' and response.status_code==200:
            file=Path(getattr(response,'path',''))
            if not file.is_file() or file.is_symlink():
                return Response('HOLD_V122_NOX_UI_FILE',status_code=409)
            try:
                js=_overlay_v122_owner_ui(file.read_bytes())
            except (ValueError,OSError,UnicodeDecodeError):
                return Response('HOLD_V122_NOX_UI_SOURCE_PIN',status_code=409)
            return Response(js,media_type='application/javascript',headers={
                'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
        if path.lstrip('/') == 'nox-function-catalog.js' and response.status_code == 200:
            file=Path(getattr(response,'path',''))
            if not file.is_file() or file.is_symlink():
                return Response('HOLD_CATALOG_FILE', status_code=409)
            try:
                js=_catalog_owner_overlay(file.read_bytes())
            except (ValueError, OSError, UnicodeDecodeError):
                return Response('HOLD_CATALOG_SOURCE_PIN', status_code=409)
            return Response(js, media_type='application/javascript', headers={
                'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
        if response.status_code != 200 or not (path.endswith('.html') or path in ('.','','/')):
            return response
        file=Path(getattr(response,'path',''))
        if not file.is_file() or file.suffix.lower()!='.html':
            return response
        raw=file.read_text(encoding='utf-8')
        if '<head>' not in raw:
            return response
        injected=raw.replace('<head>',
            '<head><script src="/nox-web-v29/native-owner.js"></script>',1)
        return HTMLResponse(injected, headers={
            'Cache-Control':'no-store',
            'X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'same-origin'})

def register_native_v29_chat(app, trusted:dict, site_dir=None):
    """Replace only V29 bridge handlers and augment status, preserving legacy OneHost."""
    for name in ('_session_ok','_unauthorized','_proxy_completion','nox_status'):
        if not callable(trusted.get(name)):
            raise RuntimeError('HOLD_NATIVE_OWNER_CALLBACK_'+name)
    existing={getattr(r,'path','') for r in app.routes}
    if '/api/nox/chat/stream' in existing or '/api/nox/stop' in existing:
        raise RuntimeError('HOLD_V29_STREAM_ALREADY_REGISTERED')
    # V108 calls register *after* legacy callbacks are defined, and adds one
    # extra status decorator after this call. Remove only previous status
    # APIRoute, replacing it with a compatible superset that comes first.
    app.router.routes[:]=[
      r for r in app.routes
      if not (isinstance(r,APIRoute) and r.path=='/api/nox/status')
    ]
    active={}

    def check(request):
        return bool(trusted['_session_ok'](request))

    def scope(request):
        if not request.cookies:
            return None
        raw=json.dumps(sorted(request.cookies.items()),separators=(',',':'))
        return hashlib.sha256(raw.encode()).hexdigest()

    @app.get('/api/nox/status')
    async def v29_owner_status(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        try:
            raw=await trusted['nox_status']()
            if isinstance(raw,dict):
                base=dict(raw)
            else:
                base=json.loads(raw.body) if hasattr(raw,'body') else {}
            if not isinstance(base,dict):
                base={}
        except Exception:
            base={}
        model=_model_name(base)
        return JSONResponse({
           **base, 'backend':'EXISTING_NATIVE_ONEHOST',
           'native_p02_bound':bool(model and callable(trusted['_proxy_completion'])),
           'primary_model':model or None,
           'native_cognitive_memory_bound':_s03_ready(),
           'native_dialogs_ready':_schema_ready(),
        },headers={'Cache-Control':'no-store'})

    @app.get('/api/ui/capabilities')
    async def native_capabilities(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        return {'schema':'NOX_NATIVE_UI_WORKSPACE_V1','tools':[],
                'projects':False,'settings':False,
                'persistent_threads':_schema_ready(),'stream':True}

    @app.get('/api/ui/memory/dialogs/status')
    async def dialogs_status(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        ready=_schema_ready()
        return {'status':'READY' if ready else 'HOLD',
                'persistent_threads':ready,
                'backing_store':'EXISTING_S03_SQLITE' if ready else None}

    @app.get('/api/ui/memory/dialogs')
    async def dialogs_list(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        if not _schema_ready():
            return JSONResponse({'status':'HOLD','reason':'S03_DIALOG_SCHEMA_MISSING'},status_code=503)
        q=request.query_params.get('q','').strip()[:240].replace('%','\\%').replace('_','\\_')
        archived=request.query_params.get('archived','false')=='true'
        try:
            with _db() as db:
                rows=db.execute(
                  "SELECT * FROM nox_v29_dialogs WHERE owner=? AND archived=? "
                  "AND title LIKE ? ESCAPE '\\' ORDER BY updated_at DESC LIMIT 80",
                  (OWNER,int(archived),'%'+q+'%')).fetchall()
            return {'status':'READY','dialogs':[_row(x) for x in rows]}
        except (OSError,RuntimeError,sqlite3.Error):
            return JSONResponse({'status':'HOLD','reason':'S03_DIALOG_READ_FAILED'},status_code=503)

    @app.post('/api/ui/memory/dialogs/create')
    async def dialogs_create(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        try:body=await request.json()
        except Exception:return JSONResponse({'error':'INVALID_JSON'},status_code=400)
        if not isinstance(body,dict) or body.get('confirmed') is not True:
            return JSONResponse({'error':'CONFIRMATION_REQUIRED'},status_code=422)
        title=body.get('title')
        if not isinstance(title,str) or not title.strip():
            return JSONResponse({'error':'INVALID_TITLE'},status_code=422)
        title=title.strip()[:140]
        if not _schema_ready():
            return JSONResponse({'status':'HOLD','reason':'S03_DIALOG_SCHEMA_MISSING'},status_code=503)
        id=uuid.uuid4().hex
        now=_now()
        try:
            with _db(True) as db:
                db.execute('INSERT INTO nox_v29_dialogs '
                           '(dialog_id,owner,title,created_at,updated_at) VALUES(?,?,?,?,?)',
                           (id,OWNER,title,now,now))
                row=_get_dialog(db,id)
            return _row(row)
        except (OSError,RuntimeError,sqlite3.Error):
            return JSONResponse({'status':'HOLD','reason':'S03_DIALOG_CREATE_FAILED'},status_code=503)

    @app.get('/api/ui/memory/dialogs/history')
    async def dialogs_history(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        id=request.query_params.get('dialog_id','')
        try:limit=max(1,min(int(request.query_params.get('limit','100')),100))
        except ValueError:return JSONResponse({'error':'INVALID_LIMIT'},status_code=422)
        if not _schema_ready():
            return JSONResponse({'status':'HOLD','reason':'S03_DIALOG_SCHEMA_MISSING'},status_code=503)
        try:
            with _db() as db:
                row=_get_dialog(db,id)
                if row is None:
                    return JSONResponse({'error':'DIALOG_NOT_FOUND'},status_code=404)
                msgs=db.execute(
                   'SELECT role,content,ts,exchange_id FROM nox_v29_dialog_messages '
                   'WHERE dialog_id=? ORDER BY row_id DESC LIMIT ?',
                   (id,limit)).fetchall()
            return {'status':'READY','dialog_id':id,'revision':row['revision'],
                    'messages':[{'role':x['role'],'content':x['content'],'ts':x['ts'],
                                 'exchange_id':x['exchange_id']} for x in reversed(msgs)]}
        except (OSError,RuntimeError,sqlite3.Error):
            return JSONResponse({'status':'HOLD','reason':'S03_DIALOG_HISTORY_FAILED'},status_code=503)

    @app.post('/api/ui/memory/dialogs/update')
    async def dialogs_update(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        try:data=await request.json()
        except Exception:return JSONResponse({'error':'INVALID_JSON'},status_code=400)
        if not isinstance(data,dict) or data.get('confirmed') is not True:
            return JSONResponse({'error':'CONFIRMATION_REQUIRED'},status_code=422)
        id=data.get('dialog_id')
        revision=data.get('revision')
        if not isinstance(revision,int) or isinstance(revision,bool) or revision<1:
            return JSONResponse({'error':'INVALID_REVISION'},status_code=422)
        if not _schema_ready():
            return JSONResponse({'status':'HOLD','reason':'S03_DIALOG_SCHEMA_MISSING'},status_code=503)
        try:
            with _db(True) as db:
                row=_get_dialog(db,id)
                if row is None:
                    return JSONResponse({'error':'DIALOG_NOT_FOUND'},status_code=404)
                if row['revision']!=revision:
                    return JSONResponse({'error':'REVISION_CONFLICT'},status_code=409)
                title=data.get('title',row['title'])
                archived=data.get('archived',bool(row['archived']))
                if not isinstance(title,str) or not title.strip() or not isinstance(archived,bool):
                    return JSONResponse({'error':'INVALID_CHANGE'},status_code=422)
                stamp=_now()
                db.execute('UPDATE nox_v29_dialogs SET title=?,archived=?,'
                           'revision=revision+1,updated_at=? WHERE owner=? AND dialog_id=?',
                           (title.strip()[:140],int(archived),stamp,OWNER,id))
                updated=_get_dialog(db,id)
            return _row(updated)
        except (OSError,RuntimeError,sqlite3.Error):
            return JSONResponse({'status':'HOLD','reason':'S03_DIALOG_UPDATE_FAILED'},status_code=503)

    @app.post('/api/nox/chat/stream')
    async def native_v29_stream(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        try:data=await request.json()
        except Exception:return JSONResponse({'error':'INVALID_JSON'},status_code=400)
        if not isinstance(data,dict):
            return JSONResponse({'error':'INVALID_BODY'},status_code=400)
        question=data.get('message')
        if not isinstance(question,str) or not 1<=len(question.strip())<=8000:
            return JSONResponse({'error':'INVALID_MESSAGE'},status_code=422)
        try:history=_validated_history(data)
        except ValueError as ex:return JSONResponse({'error':str(ex)},status_code=422)
        dialog_id=data.get('dialog_id')
        if not isinstance(dialog_id,str) or not ID_PATTERN.fullmatch(dialog_id):
            return JSONResponse({'error':'HOLD_DIALOG_SCOPE_NOT_BOUND'},status_code=409)
        if dialog_id:
            if not _schema_ready():
                return JSONResponse({'error':'HOLD_S03_DIALOG_SCHEMA'},status_code=503)
            try:
                issue,history=await asyncio.to_thread(_dialog_context,dialog_id)
                if issue:
                    return JSONResponse({'error':issue},status_code=409)
            except (OSError,RuntimeError,sqlite3.Error):
                return JSONResponse({'error':'HOLD_DIALOG_SCOPE_NOT_VERIFIED'},status_code=503)
        elif dialog_id is not None and not isinstance(dialog_id,str):
            return JSONResponse({'error':'INVALID_DIALOG_ID'},status_code=422)
        key=scope(request)
        if key is None:
            return JSONResponse({'error':'HOLD_SESSION_COOKIE_SCOPE'},status_code=401)
        if key in active:
            return JSONResponse({'error':'HOLD_ACTIVE_SESSION_STREAM'},status_code=409)
        cancel=asyncio.Event()
        active[key]=cancel
        payload={'messages':history+[{'role':'user','content':question}],
                 '_owner':True,'stream':True}
        started=time.time()

        async def generate():
            wire=None;buffer='';answer='';complete=False
            try:
                yield _jsonl({'type':'preparing','stream_mode':'NATIVE_TOKEN_STREAM'})
                wire=await trusted['_proxy_completion'](payload)
                if not hasattr(wire,'body_iterator'):
                    yield _jsonl({'type':'error','error':'HOLD_NATIVE_STREAM_MISSING'})
                    return
                yield _jsonl({'type':'start','model':'NOX HELION','stream_mode':'NATIVE_TOKEN_STREAM'})
                decoder=codecs.getincrementaldecoder('utf8')('strict')
                upstream=wire.body_iterator.__aiter__()
                while True:
                    event,chunk=await _next_native_chunk_or_stop(upstream,cancel)
                    if event=='stop':
                        yield _jsonl({'type':'error','error':'STREAM_STOP_REQUESTED'})
                        return
                    if event=='eof':
                        break
                    try:
                        buffer+=decoder.decode(chunk if isinstance(chunk,bytes) else str(chunk).encode())
                    except UnicodeDecodeError:
                        # Do not silently replace corrupted upstream bytes; an
                        # otherwise matching S03 row must not certify this text.
                        yield _jsonl({'type':'error','error':'HOLD_UPSTREAM_SSE_UTF8_INVALID'})
                        return
                    # A read may contain many *complete* short SSE frames.
                    # Limit each frame and its unfinished tail, not the whole
                    # transport chunk (which may exceed 300 KB legitimately).
                    frames=buffer.split('\n')
                    buffer=frames.pop()
                    if len(buffer)>300000 or any(len(row)>300000 for row in frames):
                        yield _jsonl({'type':'error','error':'HOLD_SSE_FRAME_LIMIT'})
                        return
                    for row in frames:
                        frame=row.strip()
                        if not frame:
                            continue
                        # An upstream [DONE] is terminal. Extra nonblank SSE
                        # frames must not fabricate a trustworthy S03 receipt.
                        if complete:
                            yield _jsonl({'type':'error','error':'HOLD_SSE_FRAME_AFTER_DONE'})
                            return
                        kind,part=_sse_delta(frame)
                        if kind=='upstream_finish_incomplete':
                            yield _jsonl({'type':'error','error':'HOLD_UPSTREAM_FINISH_REASON'})
                            return
                        if kind=='upstream_error':
                            yield _jsonl({'type':'error','error':'HOLD_UPSTREAM_SSE_ERROR'})
                            return
                        if kind=='malformed':
                            yield _jsonl({'type':'error','error':'HOLD_UPSTREAM_SSE_MALFORMED'})
                            return
                        if kind=='done':complete=True
                        if kind=='delta':
                            if len(answer)+len(part)>2000000:
                                yield _jsonl({'type':'error','error':'HOLD_OUTPUT_SIZE'})
                                return
                            answer+=part
                            yield _jsonl({'type':'delta','text':part})
                # Finalize incremental UTF-8 state: an incomplete multibyte
                # suffix must not disappear after a valid terminal [DONE].
                try:
                    buffer+=decoder.decode(b'',final=True)
                except UnicodeDecodeError:
                    yield _jsonl({'type':'error','error':'HOLD_UPSTREAM_SSE_UTF8_INVALID'})
                    return
                # EOF does not certify an unterminated SSE row. Fail closed
                # rather than discarding a post-DONE frame and claiming S03.
                if buffer.strip():
                    yield _jsonl({'type':'error','error':
                        'HOLD_SSE_FRAME_AFTER_DONE' if complete else 'HOLD_SSE_UNTERMINATED_FRAME'})
                    return
                if cancel.is_set():
                    yield _jsonl({'type':'error','error':'STREAM_STOP_REQUESTED'})
                    return
                if not complete or not answer.strip():
                    yield _jsonl({'type':'error','error':'HOLD_INCOMPLETE_NATIVE_RESPONSE'})
                    return
                proof=None
                for attempt in range(4):
                    proof=await asyncio.to_thread(_readback,question,answer,started)
                    if proof is not None:break
                    if attempt<3:await asyncio.sleep(.12)
                if proof is None:
                    yield _jsonl({'type':'error','error':'HOLD_S03_COMMIT_NOT_VERIFIED'})
                    return
                if not await asyncio.to_thread(_save_exchange,dialog_id,question,answer,proof['record_id']):
                    yield _jsonl({'type':'error','error':'HOLD_S03_DIALOG_COMMIT_NOT_VERIFIED'})
                    return
                yield _jsonl({'type':'done','model':'NOX HELION','saved':True,
                              's03_integrated':True,'dialog_id':dialog_id,
                              'exchange_id':proof['record_id'],'stream_mode':'NATIVE_TOKEN_STREAM'})
            except asyncio.CancelledError:
                raise
            except Exception:
                yield _jsonl({'type':'error','error':'HOLD_EXISTING_ONEHOST_RUNTIME'})
            finally:
                if active.get(key) is cancel:active.pop(key,None)
                if wire is not None and hasattr(getattr(wire,'body_iterator',None),'aclose'):
                    try:await wire.body_iterator.aclose()
                    except Exception:pass
        return StreamingResponse(generate(),media_type='application/x-ndjson',
            headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.post('/api/nox/stop')
    async def stream_stop(request:Request):
        if not check(request):
            return trusted['_unauthorized']()
        key=scope(request)
        if key is None or key not in active:
            return JSONResponse({'status':'HOLD','reason':'NO_ACTIVE_SESSION_STREAM'},status_code=409)
        active[key].set()
        return {'status':'STOP_REQUESTED','stream_cancellation_signalled':True,
                'gpu_stop_verified':False}

    directory=Path(site_dir) if site_dir is not None else SITE
    if directory.is_dir() and (directory/'nox-chat.js').is_file():
        if not any(getattr(r,'path','')=='/nox-web-v29' for r in app.routes):
            app.mount('/nox-web-v29',_OwnerStatic(directory,check,trusted['_unauthorized']),
                      name='nox-web-v29-owner-staging')
            mounted=app.router.routes[-1]
            app.router.routes.remove(mounted)
            app.router.routes.insert(0,mounted)
