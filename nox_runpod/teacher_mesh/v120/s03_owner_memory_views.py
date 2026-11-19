"""V120: real owner-only S03 memory/history adapters for frozen WEB V29.
Uses one existing S03 SQLite, preserves source/provenance, returns authorized
read-only records, no new database, no mock results and no write operations.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse

OWNER='nox-single-owner'

def _connect():
    import s03_memory
    p=Path(s03_memory.DB)
    if not p.is_file() or p.is_symlink():raise RuntimeError('HOLD_EXISTING_S03_MISSING')
    con=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=3)
    con.execute('PRAGMA query_only=ON')
    con.row_factory=sqlite3.Row
    return con

def _metadata(raw):
    # Existing S03 writer owns this JSON; never trust it to change record identity.
    if not isinstance(raw,str) or len(raw)>16000:
        return {}
    try:
        data=json.loads(raw)
        return data if isinstance(data,dict) else {}
    except (ValueError,TypeError):
        return {}


def _knowledge(q:str='',facts_only:bool=False,limit:int=32):
    if not isinstance(q,str) or len(q)>240 or not isinstance(limit,int) or not 1<=limit<=50:
        raise RuntimeError('HOLD_S03_QUERY_BOUNDS')
    with _connect() as db:
        cols={str(r[1]) for r in db.execute('PRAGMA table_info(s03_items)')}
        if not {'id','segment','text','provenance','sha256','ts','meta'}.issubset(cols):
            raise RuntimeError('HOLD_NATIVE_S03_SCHEMA')
        clauses=[];params=[]
        if facts_only:
            clauses.append('segment=?');params.append('M2')
        if q:
            # Native V125 stores the literal key in provenance; native V130
            # puts the key in original S03 meta.fact_key. Both must be found.
            # instr() is case-insensitive here and doesn't interpret wildcards.
            escaped=json.dumps(q,ensure_ascii=True)[1:-1]
            clauses.append("(instr(lower(COALESCE(text,'')),lower(?))>0 OR "
                           "instr(lower(COALESCE(provenance,'')),lower(?))>0 OR "
                           "instr(lower(COALESCE(meta,'')),lower(?))>0 OR "
                           "instr(lower(COALESCE(meta,'')),lower(?))>0)")
            params.extend([q,q,q,escaped])
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        sql=('SELECT id,segment,text,provenance,sha256,ts,meta FROM s03_items'
             +where+' ORDER BY ts DESC,rowid DESC LIMIT ?')
        params.append(limit)
        rows=db.execute(sql,tuple(params)).fetchall()
    results=[]
    for row in rows:
        meta=_metadata(row['meta'])
        fact_key=meta.get('fact_key')
        if not isinstance(fact_key,str) or not 1<=len(fact_key)<=160:
            fact_key=str(row['id'])
        # The original S03 row SHA can hash structured source/metadata, not
        # only note text. V130 POST returns the SHA256 of the actual UTF-8
        # content. Expose that under source_sha256 for V29 readback, while
        # returning the original S03 digest unmodified as record_sha256.
        native_sha=str(row['sha256'] or '')[:64]
        actual_text=str(row['text'] or '')
        submitted=meta.get('source_sha256')
        source_content_sha=(submitted if isinstance(submitted,str)
                            and re.fullmatch(r'[0-9a-f]{64}',submitted)
                            and submitted==hashlib.sha256(actual_text.encode('utf8')).hexdigest()
                            else None)
        results.append({
            'id':str(row['id'])[:150],
            'fact_key':fact_key[:160],
            'content':actual_text[:5000],
            'segment':str(row['segment'] or '')[:14],
            'source_ref':str(row['provenance'] or '')[:350],
            'source_sha256':source_content_sha if source_content_sha is not None else native_sha,
            'record_sha256':native_sha,
            'submitted_content_sha256':source_content_sha,
            'schema':str(meta.get('schema') or '')[:80],
            'owner_scope':str(meta.get('owner_scope') or '')[:80],
            'valid_from':str(meta.get('valid_from') or '')[:45],
            'recorded_at':str(row['ts'] or '')[:55],
        })
    return results

def _history(limit:int=50):
    with _connect() as db:
        present={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'nox_v29_dialogs','nox_v29_dialog_messages'}.issubset(present):
            raise RuntimeError('HOLD_NATIVE_DIALOG_SCHEMA')
        msgs=db.execute(
            "SELECT m.dialog_id,m.exchange_id,m.role,m.content,m.ts "
            "FROM nox_v29_dialog_messages AS m "
            "INNER JOIN nox_v29_dialogs AS d ON m.dialog_id=d.dialog_id "
            "WHERE d.owner=? AND d.archived=0 "
            "ORDER BY m.row_id DESC LIMIT ?",
            (OWNER,limit)).fetchall()
    return [{'dialog_id':str(x['dialog_id'])[:45],
             'exchange_id':str(x['exchange_id'])[:140],
             'role':str(x['role'])[:12],
             'content':str(x['content'] or '')[:5000],
             'ts':str(x['ts'] or '')[:50]} for x in reversed(msgs)]

def register_nox_v120_s03_memory_views(app,trusted):
    session=trusted.get('_session_ok')
    reject=trusted.get('_unauthorized')
    if not callable(session) or not callable(reject):
        raise RuntimeError('HOLD_OWNER_AUTH_REQUIRED')
    paths=('/api/nox/history','/api/nox/experience','/api/ui/memory/facts/history')
    existing={getattr(r,'path','') for r in app.routes}
    if any(p in existing for p in paths):raise RuntimeError('HOLD_MEMORY_ROUTE_CONFLICT')
    async def guarded(request,fn):
        if not session(request):return reject()
        try:
            result=await asyncio.wait_for(asyncio.to_thread(fn),timeout=7)
            return JSONResponse(result,headers={'Cache-Control':'no-store'})
        except Exception as exc:
            value=str(exc)
            return JSONResponse({'status':'HOLD',
                'reason':value if value.startswith('HOLD_') and len(value)<100 else 'HOLD_S03_READ'},
                status_code=503)
    @app.get('/api/nox/history')
    async def owner_s03_history(request:Request):
        return await guarded(request,lambda:{
            'status':'READY','messages':_history(),
            'source':'EXISTING_NATIVE_S03_OWNER_DIALOGS'})
    @app.get('/api/nox/experience')
    async def owner_s03_experience(request:Request):
        q=request.query_params.get('q','')
        if len(q)>240:return JSONResponse({'error':'QUERY_TOO_LONG'},status_code=422)
        return await guarded(request,lambda:{
            'status':'READY','results':_knowledge(q=q,limit=32),
            'source':'EXISTING_S03_ITEMS','semantic_embedding_search_verified':False})
    @app.get('/api/ui/memory/facts/history')
    async def owner_s03_facts(request:Request):
        q=request.query_params.get('fact_key','')
        if len(q)>160:return JSONResponse({'error':'FACT_KEY_TOO_LONG'},status_code=422)
        return await guarded(request,lambda:{
            'status':'READY','events':_knowledge(q=q,facts_only=True,limit=32),
            'source':'EXISTING_S03_M2','fact_supersession_chain_verified':False})
