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
from owner_chat_request_ledger import RequestLedger, LedgerError, SCHEMA as REQUEST_SCHEMA, request_id as validate_request_id

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
        if write: conn.execute('PRAGMA synchronous=FULL')
        with conn:
            yield conn
    finally:
        conn.close()

def ensure_dialog_schema():
    """Add only two tables and indexes inside preexisting S03 SQLite (no new DB)."""
    with _db(True) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='s03_items'").fetchone() is None:
            raise RuntimeError('HOLD_ORIGINAL_S03_SCHEMA')
        db.executescript(SCHEMA + REQUEST_SCHEMA)
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
    history=data.get('history') or []
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
    """Load only the authenticated owner's committed pairs from the existing S03.

    The Resonance client deliberately sends history=[] and a dialog_id. Its
    displayed history is not an inference payload. Use the durable thread as
    the authority, with the same 24-message/121 KB context limits as the
    legacy client path. Incomplete pairs cannot enter model context.
    """
    with _db() as db:
        found=_get_dialog(db,dialog_id)
        if found is None:
            return 'HOLD_DIALOG_SCOPE_NOT_BOUND',[]
        if bool(found['archived']):
            return 'HOLD_DIALOG_ARCHIVED',[]
        rows=db.execute(
            'SELECT substr(u.content,1,8000) AS question, '
            'substr(a.content,1,8000) AS answer '
            'FROM nox_v29_dialog_messages AS a '
            'JOIN nox_v29_dialog_messages AS u '
            'ON u.dialog_id=a.dialog_id AND u.exchange_id=a.exchange_id '
            "AND u.role='user' WHERE a.dialog_id=? AND a.role='assistant' "
            'ORDER BY a.row_id DESC LIMIT 12',(dialog_id,)).fetchall()
    pairs=[];size=0
    for row in rows:
        question,answer=row['question'],row['answer']
        if not isinstance(question,str) or not isinstance(answer,str):
            raise RuntimeError('HOLD_S03_DIALOG_CONTEXT_CONTENT')
        pair_size=len(question.encode('utf-8'))+len(answer.encode('utf-8'))
        if size+pair_size>121000:
            break
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

def _register_mini_tasks(app, trusted, check, site_dir=None):
    """Owner-only mini inbox on this OneHost; never runs code or opens a dialog."""
    import importlib
    root = Path('/root/nox')
    principal = OWNER + ':mini-v1'
    web_root = Path(site_dir) if site_dir is not None else SITE
    client_id = re.compile(r'^[A-Za-z0-9._:-]{8,80}$')
    task_id = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')
    prefix = '/api/ui/mini'
    paths = {prefix+'/capabilities', prefix+'/tasks', prefix+'/tasks/by-request/{request_id}', prefix+'/tasks/{task_id}'}
    if any(getattr(route,'path','') in paths for route in app.routes):
        raise RuntimeError('HOLD_MINI_ROUTES_ALREADY_REGISTERED')

    def adapter():
        module = importlib.import_module('owner_mini_tasks')
        if not all(callable(getattr(module,name,None)) for name in ('capabilities','submit','lookup','lookup_request','list_tasks')):
            raise RuntimeError('HOLD_MINI_QUEUE_BINDING')
        return module

    def failure(exc, default='HOLD_MINI_QUEUE_UNAVAILABLE'):
        reason = getattr(exc,'code',str(exc))
        if not re.fullmatch(r'(?:HOLD|WAIT|INVALID|NOT_FOUND|CONFLICT|MINI)_[A-Z0-9_]{1,100}',reason):
            reason=default
        code = getattr(exc,'http_status',503)
        if type(code) is not int or code not in (400,403,404,409,413,422,423,429,503):code=503
        return JSONResponse({'schema':'NOX_MINI_TASK_V1','state':'UNCONFIRMED','error':reason,
                             'execution_started':False},status_code=code,headers={'Cache-Control':'no-store'})

    def project(value):
        if not isinstance(value,dict):
            raise RuntimeError('HOLD_MINI_QUEUE_RECEIPT')
        return {'schema':'NOX_MINI_TASK_V1',**{key:value[key] for key in ('schema','task_id','request_id','state','replayed','queue',
                'execution_started','accepted','pending','reason','receipt_id','intent','status','updated_at','context','executable','planner_pending','queue_state','plan_id','plan_revision','receipt_refs','planning_state','plan_proposal') if key in value}}

    def page_context(value):
        if not isinstance(value,dict) or set(value)-{'page_path','title','theme','scope','selected_object'}:
            raise ValueError('INVALID_MINI_CONTEXT')
        name=value.get('page_path')
        if (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+\.html',name)
                or name.startswith('/') or '..' in name.split('/') or len(name)>240
                or value.get('scope') not in ('page','site')
                or not isinstance(value.get('title'),str) or len(value['title'])>180
                or not isinstance(value.get('theme'),str) or len(value['theme'])>80):
            raise ValueError('INVALID_MINI_CONTEXT')
        target=web_root/name
        if not target.is_file() or any(part.is_symlink() for part in (target,*target.parents)):
            raise ValueError('INVALID_MINI_PAGE')
        selected=value.get('selected_object')
        if selected is not None and (not isinstance(selected,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',selected)):
            raise ValueError('INVALID_MINI_OBJECT')
        return dict(value)

    @app.get(prefix+'/capabilities')
    async def mini_capabilities(request:Request):
        if not check(request):return trusted['_unauthorized']()
        try:
            value=await asyncio.to_thread(adapter().capabilities,root,principal)
            if not isinstance(value,dict):raise RuntimeError('HOLD_MINI_QUEUE_CAPABILITIES')
            enabled=value.get('available') is True
            return JSONResponse({'schema':'NOX_MINI_CAPABILITIES_V1','commands_supported':enabled,
                'namespace':'mini-v1','queue':'existing_dispatcher','cancel_supported':False,
                'status_by_request':True,'max_text_chars':8000,
                'typed_intents':value.get('typed_intents',[]),'free_text':value.get('free_text','draft'),
                'owner_stop':value.get('owner_stop') is True,'scopes':value.get('scopes',['page','site']),
                'route_map_sha256':value.get('route_map_sha256'),
                'reason':value.get('reason') if isinstance(value.get('reason'),str) else None},
                headers={'Cache-Control':'no-store'})
        except Exception:
            return JSONResponse({'schema':'NOX_MINI_CAPABILITIES_V1','commands_supported':False,
                'namespace':'mini-v1','queue':'existing_dispatcher','cancel_supported':False,
                'status_by_request':False,'reason':'HOLD_MINI_QUEUE_UNAVAILABLE'},
                status_code=503,headers={'Cache-Control':'no-store'})

    @app.post(prefix+'/tasks')
    async def mini_submit(request:Request):
        if not check(request):return trusted['_unauthorized']()
        # JSON-only, same-origin browser writes; no callback accepts shell/handler names.
        origin=request.headers.get('origin')
        if origin != str(request.base_url).rstrip('/') or request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'error':'HOLD_MINI_ORIGIN'},status_code=403)
        if request.headers.get('content-type','').split(';',1)[0].strip().lower()!='application/json':
            return JSONResponse({'error':'INVALID_MINI_CONTENT_TYPE'},status_code=415)
        try:
            raw=bytearray()
            async for part in request.stream():
                raw.extend(part)
                if len(raw)>40000:return JSONResponse({'error':'INVALID_MINI_BODY_SIZE'},status_code=413)
            data=json.loads(bytes(raw).decode('utf-8'))
        except (ValueError,UnicodeDecodeError):
            return JSONResponse({'error':'INVALID_MINI_JSON'},status_code=400)
        if (not isinstance(data,dict) or set(data)-{'request_id','text','intent','context'}
                or not isinstance(data.get('request_id'),str) or not client_id.fullmatch(data['request_id'])
                or not isinstance(data.get('text'),str) or not 1<=len(data['text'].strip())<=8000
                or len(data['text'])>8000 or ('intent' in data and (not isinstance(data['intent'],str) or len(data['intent'])>64))):
            return JSONResponse({'error':'INVALID_MINI_COMMAND'},status_code=422)
        try:context=page_context(data.get('context'))
        except ValueError as exc:return JSONResponse({'error':str(exc)},status_code=422)
        try:
            result=await asyncio.to_thread(adapter().submit,root,principal,data['request_id'],data['text'],data.get('intent'),context)
            return JSONResponse(project(result),status_code=202,headers={'Cache-Control':'no-store'})
        except Exception as exc:return failure(exc)

    @app.get(prefix+'/tasks')
    async def mini_list(request:Request):
        if not check(request):return trusted['_unauthorized']()
        try:
            listing=await asyncio.to_thread(adapter().list_tasks,root,principal,50)
            rows=listing.get('tasks') if isinstance(listing,dict) else None
            if not isinstance(rows,list) or len(rows)>50:raise RuntimeError('HOLD_MINI_QUEUE_LIST')
            return JSONResponse({'schema':'NOX_MINI_TASK_LIST_V1','items':[project(row) for row in rows],'has_more':listing.get('has_more') is True},headers={'Cache-Control':'no-store'})
        except Exception as exc:return failure(exc)

    @app.get(prefix+'/tasks/by-request/{request_id}')
    async def mini_by_request(request_id:str,request:Request):
        if not check(request):return trusted['_unauthorized']()
        if not client_id.fullmatch(request_id):return JSONResponse({'error':'INVALID_MINI_REQUEST_ID'},status_code=422)
        try:return JSONResponse(project(await asyncio.to_thread(adapter().lookup_request,root,principal,request_id)),headers={'Cache-Control':'no-store'})
        except Exception as exc:return failure(exc)

    @app.get(prefix+'/tasks/{task_id}')
    async def mini_status(task_id:str,request:Request):
        if not check(request):return trusted['_unauthorized']()
        if not task_id or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',task_id):return JSONResponse({'error':'INVALID_MINI_TASK_ID'},status_code=422)
        try:return JSONResponse(project(await asyncio.to_thread(adapter().lookup,root,principal,task_id)),headers={'Cache-Control':'no-store'})
        except Exception as exc:return failure(exc)


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
    active_requests={}
    producer_jobs=set()
    ledger=RequestLedger(_db, OWNER)

    def check(request):
        return bool(trusted['_session_ok'](request))

    def scope(request):
        if not request.cookies:
            return None
        raw=json.dumps(sorted(request.cookies.items()),separators=(',',':'))
        return hashlib.sha256(raw.encode()).hexdigest()

    _register_mini_tasks(app, trusted, check, site_dir)

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
                'persistent_threads':_schema_ready(),'stream':True,'durable_request_ledger':ledger.ready()}

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

    async def event_response(rid, after):
        try:
            await asyncio.to_thread(ledger.events,rid,after)
        except LedgerError as error:
            return JSONResponse({'error':error.code,'request_id':rid},status_code=error.status)
        except (RuntimeError,sqlite3.Error,OSError):
            return JSONResponse({'error':'HOLD_REQUEST_LEDGER_UNAVAILABLE'},status_code=503)
        async def subscribe():
            cursor=after
            while True:
                rows,snapshot=await asyncio.to_thread(ledger.events,rid,cursor)
                for row in rows:
                    cursor=row['event_id']
                    yield _jsonl(row)
                if snapshot['terminal'] and cursor>=snapshot['last_event_id']:return
                if not rows:await asyncio.sleep(.05)
        return StreamingResponse(subscribe(),media_type='application/x-ndjson',
            headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.get('/api/nox/chat/requests/{request_id}')
    async def request_snapshot(request_id:str,request:Request):
        if not check(request):return trusted['_unauthorized']()
        try:return JSONResponse(await asyncio.to_thread(ledger.snapshot,validate_request_id(request_id)),headers={'Cache-Control':'no-store'})
        except LedgerError as error:return JSONResponse({'error':error.code},status_code=error.status)
        except (RuntimeError,sqlite3.Error,OSError):return JSONResponse({'error':'HOLD_REQUEST_LEDGER_UNAVAILABLE'},status_code=503)

    @app.get('/api/nox/chat/requests/{request_id}/events')
    async def request_events(request_id:str,request:Request,after_event_id:int=0):
        if not check(request):return trusted['_unauthorized']()
        try:rid=validate_request_id(request_id)
        except LedgerError as error:return JSONResponse({'error':error.code},status_code=error.status)
        return await event_response(rid,after_event_id)

    @app.post('/api/nox/chat/stream')
    async def native_v29_stream(request:Request):
        if not check(request):return trusted['_unauthorized']()
        try:data=await request.json()
        except Exception:return JSONResponse({'error':'INVALID_JSON'},status_code=400)
        if not isinstance(data,dict):return JSONResponse({'error':'INVALID_BODY'},status_code=400)
        question=data.get('message')
        if not isinstance(question,str) or not 1<=len(question.strip())<=8000:
            return JSONResponse({'error':'INVALID_MESSAGE'},status_code=422)
        try:
            history=_validated_history(data)
            rid=validate_request_id(data.get('request_id') or uuid.uuid4().hex)
        except ValueError as error:return JSONResponse({'error':str(error)},status_code=422)
        after=data.get('after_event_id',0)
        if type(after) is not int or after<0:return JSONResponse({'error':'INVALID_EVENT_CURSOR'},status_code=422)
        if not ledger.ready():return JSONResponse({'error':'HOLD_REQUEST_LEDGER_SCHEMA'},status_code=503)
        # Hash the caller's immutable request, not evolving server-side history.
        request_payload={'message':question,'dialog_id':data.get('dialog_id'),'history':history}
        dialog_id=data.get('dialog_id')
        if dialog_id:
            try:
                issue,history=await asyncio.to_thread(_dialog_context,dialog_id)
                if issue:return JSONResponse({'error':issue},status_code=409)
            except (OSError,RuntimeError,sqlite3.Error):
                return JSONResponse({'error':'HOLD_DIALOG_SCOPE_NOT_VERIFIED'},status_code=503)
        elif dialog_id is not None and not isinstance(dialog_id,str):
            return JSONResponse({'error':'INVALID_DIALOG_ID'},status_code=422)
        key=scope(request)
        if key is None:return JSONResponse({'error':'HOLD_SESSION_COOKIE_SCOPE'},status_code=401)
        payload={'messages':history+[{'role':'user','content':question}],'_owner':True,'stream':True}
        started=time.time()

        async def produce(rid, token, cancel):
            wire=None;buffer='';answer='';complete=False
            async def emit(event):
                return await asyncio.to_thread(ledger.append,rid,token,event)
            async def watch_stop():
                while True:
                    observed=await asyncio.to_thread(ledger.snapshot,rid)
                    if observed['terminal']:return
                    if observed['stop_requested']:cancel.set();return
                    await asyncio.sleep(.2)
            watcher=asyncio.create_task(watch_stop())
            try:
                if cancel.is_set() or (await asyncio.to_thread(ledger.snapshot,rid))['stop_requested']:
                    await emit({'type':'error','error':'STREAM_STOP_REQUESTED'});return
                opening=asyncio.create_task(trusted['_proxy_completion'](payload))
                stop_wait=asyncio.create_task(cancel.wait())
                try:
                    finished,_=await asyncio.wait((opening,stop_wait),return_when=asyncio.FIRST_COMPLETED)
                    if stop_wait in finished and stop_wait.result():
                        opening.cancel()
                        try:await opening
                        except (asyncio.CancelledError,Exception):pass
                        await emit({'type':'error','error':'STREAM_STOP_REQUESTED'});return
                    wire=await opening
                finally:
                    stop_wait.cancel()
                    try:await stop_wait
                    except (asyncio.CancelledError,Exception):pass
                if not hasattr(wire,'body_iterator'):
                    await emit({'type':'error','error':'HOLD_NATIVE_STREAM_MISSING'})
                    return
                await emit({'type':'start','model':'NOX HELION','stream_mode':'NATIVE_TOKEN_STREAM'})
                decoder=codecs.getincrementaldecoder('utf8')('strict')
                upstream=wire.body_iterator.__aiter__()
                while True:
                    event,chunk=await _next_native_chunk_or_stop(upstream,cancel)
                    if event=='stop':
                        await emit({'type':'error','error':'STREAM_STOP_REQUESTED'})
                        return
                    if event=='eof':
                        break
                    try:
                        buffer+=decoder.decode(chunk if isinstance(chunk,bytes) else str(chunk).encode())
                    except UnicodeDecodeError:
                        # Do not silently replace corrupted upstream bytes; an
                        # otherwise matching S03 row must not certify this text.
                        await emit({'type':'error','error':'HOLD_UPSTREAM_SSE_UTF8_INVALID'})
                        return
                    # A read may contain many *complete* short SSE frames.
                    # Limit each frame and its unfinished tail, not the whole
                    # transport chunk (which may exceed 300 KB legitimately).
                    frames=buffer.split('\n')
                    buffer=frames.pop()
                    if len(buffer)>300000 or any(len(row)>300000 for row in frames):
                        await emit({'type':'error','error':'HOLD_SSE_FRAME_LIMIT'})
                        return
                    for row in frames:
                        frame=row.strip()
                        if not frame:
                            continue
                        # An upstream [DONE] is terminal. Extra nonblank SSE
                        # frames must not fabricate a trustworthy S03 receipt.
                        if complete:
                            await emit({'type':'error','error':'HOLD_SSE_FRAME_AFTER_DONE'})
                            return
                        kind,part=_sse_delta(frame)
                        if kind=='upstream_finish_incomplete':
                            await emit({'type':'error','error':'HOLD_UPSTREAM_FINISH_REASON'})
                            return
                        if kind=='upstream_error':
                            await emit({'type':'error','error':'HOLD_UPSTREAM_SSE_ERROR'})
                            return
                        if kind=='malformed':
                            await emit({'type':'error','error':'HOLD_UPSTREAM_SSE_MALFORMED'})
                            return
                        if kind=='done':complete=True
                        if kind=='delta':
                            if len(answer)+len(part)>2000000:
                                await emit({'type':'error','error':'HOLD_OUTPUT_SIZE'})
                                return
                            answer+=part
                            await emit({'type':'delta','text':part})
                # Finalize incremental UTF-8 state: an incomplete multibyte
                # suffix must not disappear after a valid terminal [DONE].
                try:
                    buffer+=decoder.decode(b'',final=True)
                except UnicodeDecodeError:
                    await emit({'type':'error','error':'HOLD_UPSTREAM_SSE_UTF8_INVALID'})
                    return
                # EOF does not certify an unterminated SSE row. Fail closed
                # rather than discarding a post-DONE frame and claiming S03.
                if buffer.strip():
                    await emit({'type':'error','error':
                        'HOLD_SSE_FRAME_AFTER_DONE' if complete else 'HOLD_SSE_UNTERMINATED_FRAME'})
                    return
                if cancel.is_set():
                    await emit({'type':'error','error':'STREAM_STOP_REQUESTED'})
                    return
                if not complete or not answer.strip():
                    await emit({'type':'error','error':'HOLD_INCOMPLETE_NATIVE_RESPONSE'})
                    return
                proof=None
                for attempt in range(4):
                    proof=await asyncio.to_thread(_readback,question,answer,started)
                    if proof is not None:break
                    if attempt<3:await asyncio.sleep(.12)
                if proof is None:
                    await emit({'type':'error','error':'HOLD_S03_COMMIT_NOT_VERIFIED'})
                    return
                await asyncio.to_thread(ledger.complete,rid,token,proof)
            except asyncio.CancelledError:
                try:await emit({'type':'error','error':'STREAM_INTERRUPTED_HANDLER'})
                except Exception:pass
                raise
            except LedgerError as error:
                try:await emit({'type':'error','error':error.code})
                except Exception:pass
            except Exception:
                try:await emit({'type':'error','error':'HOLD_EXISTING_ONEHOST_RUNTIME'})
                except Exception:pass
            finally:
                watcher.cancel()
                try:await watcher
                except (asyncio.CancelledError,Exception):pass
                if active.get(key) == rid:active.pop(key,None)
                active_requests.pop(rid,None)
                if wire is not None and hasattr(getattr(wire,'body_iterator',None),'aclose'):
                    try:await wire.body_iterator.aclose()
                    except Exception:pass

        async def begin():
            snapshot,token=await asyncio.to_thread(ledger.accept,rid,question,dialog_id,request_payload,key)
            if token is not None:
                cancel=asyncio.Event();active[key]=rid;active_requests[rid]=cancel
                job=asyncio.create_task(produce(rid,token,cancel))
                producer_jobs.add(job);job.add_done_callback(producer_jobs.discard)
            return snapshot
        # Admission/start survives an HTTP disconnect at the await boundary.
        admission=asyncio.create_task(begin());producer_jobs.add(admission)
        admission.add_done_callback(producer_jobs.discard)
        try:await asyncio.shield(admission)
        except LedgerError as error:return JSONResponse({'error':error.code,'request_id':rid},status_code=error.status)
        except (RuntimeError,sqlite3.Error,OSError):return JSONResponse({'error':'HOLD_REQUEST_LEDGER_UNAVAILABLE'},status_code=503)
        return await event_response(rid,after)

    @app.post('/api/nox/stop')
    async def stream_stop(request:Request):
        if not check(request):return trusted['_unauthorized']()
        try:data=await request.json()
        except Exception:data={}
        if not isinstance(data,dict):return JSONResponse({'error':'INVALID_BODY'},status_code=400)
        rid=data.get('request_id')
        if rid is None:rid=active.get(scope(request))
        if rid is None:return JSONResponse({'status':'HOLD','reason':'NO_ACTIVE_SESSION_STREAM'},status_code=409)
        try:
            result=await asyncio.to_thread(ledger.stop,validate_request_id(rid))
            if rid in active_requests:
                active_requests[rid].set();result['stream_cancellation_signalled']=True
            return result
        except LedgerError as error:return JSONResponse({'error':error.code,'request_id':rid},status_code=error.status)
        except (RuntimeError,sqlite3.Error,OSError):return JSONResponse({'error':'HOLD_REQUEST_LEDGER_UNAVAILABLE'},status_code=503)

    directory=Path(site_dir) if site_dir is not None else SITE
    if directory.is_dir() and (directory/'nox-chat.js').is_file():
        if not any(getattr(r,'path','')=='/nox-web-v29' for r in app.routes):
            app.mount('/nox-web-v29',_OwnerStatic(directory,check,trusted['_unauthorized']),
                      name='nox-web-v29-owner-staging')
            mounted=app.router.routes[-1]
            app.router.routes.remove(mounted)
            app.router.routes.insert(0,mounted)
