"""V130: owner-confirmed WEB V29 note -> existing native S03 M2, with durable readback.

One NOX OneHost, one original knowledge.sqlite, native s03_memory.remember ONLY.
No new database, daemon, API token, trainer, adapter, model or synthetic success.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from fastapi import Request
from fastapi.responses import JSONResponse

_ROUTE='/api/nox/memory/facts'
_READBACK_ROUTE='/api/ui/memory/facts/exact-readback'
_OWNER='nox-single-owner'
_HEX=re.compile(r'^[a-f0-9]{64}$')
_STOP=('/root/nox/state/STOP.flag','/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
       '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')

def _hold(reason, code=503):
    return JSONResponse({'status':'HOLD','reason':reason},status_code=code,
          headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

def _stopped():
    """Fail closed on original owner STOP markers, including dangling symlinks.

    pathlib.Path.exists() is False for a broken symlink: treating that as
    STOP=off could allow native S03 writes despite an owner STOP sentinel.
    An inaccessible marker is also not evidence that it is absent.
    """
    try:
        for name in _STOP:
            marker=Path(name)
            if marker.exists() or marker.is_symlink():
                return True
    except OSError:
        return True
    return False

def _safe_request(request):
    site=request.headers.get('sec-fetch-site','')
    if site=='same-origin':
        # Browser-generated Fetch Metadata identifies the owner host even when
        # the existing reverse proxy forwards the request to localhost:8080.
        return True
    if site not in ('','none'):
        return False
    origin=request.headers.get('origin','')
    if not origin:
        return True
    # Non-browser clients without Fetch Metadata must use actual same origin.
    expected=str(request.base_url).rstrip('/')
    return origin==expected

def _validate(payload):
    if not isinstance(payload,dict) or len(payload)>8:
        raise ValueError('HOLD_FACT_BODY_SCHEMA')
    fields=('fact_key','content','valid_from','source_ref','source_sha256')
    if any(not isinstance(payload.get(k),str) for k in fields):
        raise ValueError('HOLD_FACT_FIELDS')
    title=payload['fact_key'].strip()
    content=payload['content'].strip()
    src=payload['source_ref'].strip()
    if not 1<=len(title)<=128 or not 2<=len(content)<=4096 or not 1<=len(src)<=180:
        raise ValueError('HOLD_FACT_BOUNDS')
    if any(ord(c)<32 or ord(c)==127 for c in title+src):
        raise ValueError('HOLD_FACT_CONTROL_CHARS')
    if '\x00' in content:
        raise ValueError('HOLD_FACT_CONTENT')
    stamp=payload['valid_from']
    if not 15<=len(stamp)<=45:
        raise ValueError('HOLD_FACT_DATE')
    try:
        parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'))
    except ValueError as exc:
        raise ValueError('HOLD_FACT_DATE') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('HOLD_FACT_DATE_TZ')
    expected=hashlib.sha256(content.encode('utf8')).hexdigest()
    if not _HEX.fullmatch(payload['source_sha256']) or payload['source_sha256']!=expected:
        raise ValueError('HOLD_FACT_CONTENT_SHA')
    if len(content.encode('utf8'))>16000:
        raise ValueError('HOLD_FACT_BYTES')
    return {'fact_key':title,'content':content,'valid_from':stamp,
            'source_ref':src,'source_sha256':expected}

def _conn():
    import s03_memory
    p=Path(s03_memory.DB)
    if not p.is_file() or p.is_symlink():
        raise RuntimeError('HOLD_ORIGINAL_S03_UNAVAILABLE')
    db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=5)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    return db

def _matching(data):
    # Read-only proof. Private content never leaves the original host.
    with _conn() as db:
        required={'id','segment','text','provenance','sha256','meta','ts'}
        cols={str(r[1]) for r in db.execute('PRAGMA table_info(s03_items)')}
        if not required.issubset(cols):
            raise RuntimeError('HOLD_ORIGINAL_S03_SCHEMA')
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('HOLD_ORIGINAL_S03_INTEGRITY')
        # Never infer "not found" from only the newest 100 same-text rows:
        # unrelated fact_keys may bury an older valid owner-confirmed key.
        # Keyset pagination is read-only. Fail closed on a pathological scan
        # rather than issue a second native S03 write with false idempotency.
        found=[]
        cursor=None
        scanned=0
        while True:
            query=("SELECT rowid AS _nox_rowid,id,sha256,provenance,meta,ts FROM s03_items "
                   "WHERE segment='M2' AND text=? AND provenance=?")
            params=[data['content'],'OWNER-CONFIRMED:'+data['source_ref']]
            if cursor is not None:
                query+=" AND rowid<?"
                params.append(cursor)
            rows=db.execute(query+" ORDER BY rowid DESC LIMIT 100",params).fetchall()
            for row in rows:
                # Original S03 row digest can hash structured/provenance fields,
                # not just the submitted UTF-8 note. Verify it as native evidence,
                # while the owner-supplied source_sha256 remains the text digest.
                native_sha=str(row['sha256'] or '')
                if not _HEX.fullmatch(native_sha):
                    continue
                if row['provenance']!='OWNER-CONFIRMED:'+data['source_ref']:
                    continue
                try:
                    meta=json.loads(row['meta']) if isinstance(row['meta'],str) else {}
                except (ValueError,TypeError):
                    continue
                if (isinstance(meta,dict) and meta.get('owner_scope')==_OWNER
                    and meta.get('schema')=='NOX_OWNER_CONFIRMED_FACT_V1'
                    and meta.get('source_ref')==data['source_ref']
                    and meta.get('fact_key')==data['fact_key']
                    and meta.get('source_sha256')==data['source_sha256']
                    and meta.get('valid_from')==data['valid_from']
                    and isinstance(row['id'],str) and len(row['id'])>=6):
                    found.append({'id':row['id'],'record_sha256':native_sha,
                                  'content_sha256':data['source_sha256']})
            if found:
                return found
            scanned+=len(rows)
            if len(rows)<100:
                break
            if scanned>=10000:
                raise RuntimeError('HOLD_S03_MATCH_SCAN_BUDGET')
            cursor=rows[-1]['_nox_rowid']
        return found

def _persist(data):
    if _stopped():
        raise RuntimeError('HOLD_NATIVE_STOP')
    before=_matching(data)
    if before:
        return {'status':'READY','event_id':before[0]['id'],'id':before[0]['id'],
                'source_sha256':before[0]['content_sha256'],
                'record_sha256':before[0]['record_sha256'],
                'duplicate':True,'committed':True,'readback_verified':True,
                'source':'EXISTING_NATIVE_S03_M2','weight_update':False}
    import s03_memory
    if not callable(getattr(s03_memory,'remember',None)):
        raise RuntimeError('HOLD_NATIVE_S03_WRITER')
    meta={'schema':'NOX_OWNER_CONFIRMED_FACT_V1','owner_scope':_OWNER,
          'fact_key':data['fact_key'],'source_ref':data['source_ref'],
          'source_sha256':data['source_sha256'],'valid_from':data['valid_from']}
    # The bounded readback scan may outlive a new owner STOP request.
    if _stopped():
        raise RuntimeError('HOLD_NATIVE_STOP')
    # Existing S03 writer handles SQLite transaction, IDs and its own ledger.
    s03_memory.remember(text=data['content'],segment='M2',
      provenance='OWNER-CONFIRMED:'+data['source_ref'],salience=0.85,meta=meta)
    after=_matching(data)
    prior_ids={x['id'] for x in before}
    created=next((x for x in after if x['id'] not in prior_ids),None)
    if created is None:
        raise RuntimeError('HOLD_S03_WRITE_READBACK')
    return {'status':'READY','event_id':created['id'],'id':created['id'],
            'source_sha256':created['content_sha256'],
            'record_sha256':created['record_sha256'],
            'duplicate':False,'committed':True,'readback_verified':True,
            'source':'EXISTING_NATIVE_S03_M2','weight_update':False}

def _validate_readback(payload):
    fields=('event_id','fact_key','source_ref','valid_from','source_sha256','record_sha256')
    if not isinstance(payload,dict) or set(payload)!=set(fields):
        raise ValueError('HOLD_FACT_READBACK_FIELDS')
    clean={}
    for key in fields:
        value=payload.get(key)
        if not isinstance(value,str) or value!=value.strip() or not value:
            raise ValueError('HOLD_FACT_READBACK_FIELDS')
        if any(ord(c)<32 or ord(c)==127 for c in value):
            raise ValueError('HOLD_FACT_READBACK_FIELDS')
        clean[key]=value
    if not 6<=len(clean['event_id'])<=160:
        raise ValueError('HOLD_FACT_READBACK_EVENT_ID')
    if not 1<=len(clean['fact_key'])<=128 or not 1<=len(clean['source_ref'])<=180:
        raise ValueError('HOLD_FACT_READBACK_BOUNDS')
    stamp=clean['valid_from']
    if not 15<=len(stamp)<=45:
        raise ValueError('HOLD_FACT_READBACK_DATE')
    try:
        parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'))
    except ValueError as exc:
        raise ValueError('HOLD_FACT_READBACK_DATE') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('HOLD_FACT_READBACK_DATE_TZ')
    for key in ('source_sha256','record_sha256'):
        if not _HEX.fullmatch(clean[key]):
            raise ValueError('HOLD_FACT_READBACK_SHA')
    return clean


def _exact_readback(data):
    """Independently re-read one V130 owner-confirmed M2 fact by immutable receipt."""
    with _conn() as db:
        required={'id','segment','text','provenance','sha256','meta','ts'}
        cols={str(r[1]) for r in db.execute('PRAGMA table_info(s03_items)')}
        if not required.issubset(cols):
            raise RuntimeError('HOLD_ORIGINAL_S03_SCHEMA')
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('HOLD_ORIGINAL_S03_INTEGRITY')
        rows=db.execute(
            'SELECT id,segment,text,provenance,sha256,meta,ts FROM s03_items WHERE id=? LIMIT 2',
            (data['event_id'],)).fetchall()
    if len(rows)!=1:
        return None
    row=rows[0]
    if (row['id']!=data['event_id'] or row['segment']!='M2'
            or not isinstance(row['text'],str)
            or not 2<=len(row['text'])<=4096
            or len(row['text'].encode('utf-8'))>16000
            or row['provenance']!='OWNER-CONFIRMED:'+data['source_ref']
            or not isinstance(row['sha256'],str)
            or not _HEX.fullmatch(row['sha256'])
            or row['sha256']!=data['record_sha256']):
        return None
    content_sha=hashlib.sha256(row['text'].encode('utf-8')).hexdigest()
    if content_sha!=data['source_sha256']:
        return None
    try:
        meta=json.loads(row['meta']) if isinstance(row['meta'],str) else None
    except (ValueError,TypeError):
        return None
    if (not isinstance(meta,dict)
            or meta.get('schema')!='NOX_OWNER_CONFIRMED_FACT_V1'
            or meta.get('owner_scope')!=_OWNER
            or meta.get('fact_key')!=data['fact_key']
            or meta.get('source_ref')!=data['source_ref']
            or meta.get('valid_from')!=data['valid_from']
            or meta.get('source_sha256')!=data['source_sha256']):
        return None
    return {
        'status':'READY','readback_verified':True,
        'readback_scope':'EXACT_NATIVE_S03_M2_OWNER_FACT',
        'event_id':data['event_id'],'fact_key':data['fact_key'],
        'content':row['text'],'source_ref':data['source_ref'],
        'valid_from':data['valid_from'],'source_sha256':content_sha,
        'record_sha256':row['sha256'],'segment':'M2',
        'provenance':row['provenance'],'schema':'NOX_OWNER_CONFIRMED_FACT_V1',
        'owner_scope':_OWNER
    }

def register_nox_v130_owner_fact_write(app,trusted):
    session=trusted.get('_session_ok')
    unauthorized=trusted.get('_unauthorized')
    if not callable(session) or not callable(unauthorized):
        raise RuntimeError('HOLD_OWNER_COOKIE_CALLBACK')
    if {_ROUTE,_READBACK_ROUTE} & {getattr(r,'path','') for r in app.routes}:
        raise RuntimeError('HOLD_NATIVE_ROUTE_ALREADY_EXISTS')
    lock=asyncio.Lock()

    @app.post(_ROUTE)
    async def owner_s03_fact(request:Request):
        if not session(request):
            return unauthorized()
        if not _safe_request(request):
            return _hold('HOLD_FACT_CROSS_ORIGIN',403)
        if 'application/json' not in request.headers.get('content-type','').lower():
            return _hold('HOLD_FACT_CONTENT_TYPE',415)
        data=b''
        try:
            async for part in request.stream():
                if len(data)+len(part)>20000:
                    return _hold('HOLD_FACT_REQUEST_TOO_LARGE',413)
                data+=part
            parsed=json.loads(data)
            clean=_validate(parsed)
        except (ValueError,TypeError,UnicodeDecodeError) as exc:
            reason=str(exc)
            return _hold(reason if reason.startswith('HOLD_') and len(reason)<100
                         else 'HOLD_FACT_JSON',422)
        if _stopped():
            return _hold('HOLD_NATIVE_STOP',409)
        async with lock:
            try:
                proof=await asyncio.to_thread(_persist,clean)
                return JSONResponse(proof,headers={
                    'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
            except Exception as exc:
                reason=str(exc)
                return _hold(reason if reason.startswith('HOLD_') and len(reason)<100
                             else 'HOLD_S03_NATIVE_WRITE')
    @app.post(_READBACK_ROUTE)
    async def owner_s03_fact_exact_readback(request:Request):
        if not session(request):
            return unauthorized()
        if not _safe_request(request):
            return _hold('HOLD_FACT_CROSS_ORIGIN',403)
        if 'application/json' not in request.headers.get('content-type','').lower():
            return _hold('HOLD_FACT_CONTENT_TYPE',415)
        data=b''
        try:
            async for part in request.stream():
                if len(data)+len(part)>20000:
                    return _hold('HOLD_FACT_REQUEST_TOO_LARGE',413)
                data+=part
            parsed=json.loads(data)
            clean=_validate_readback(parsed)
        except (ValueError,TypeError,UnicodeDecodeError) as exc:
            reason=str(exc)
            return _hold(reason if reason.startswith('HOLD_') and len(reason)<100
                         else 'HOLD_FACT_JSON',422)
        try:
            proof=await asyncio.to_thread(_exact_readback,clean)
        except Exception as exc:
            reason=str(exc)
            return _hold(reason if reason.startswith('HOLD_') and len(reason)<100
                         else 'HOLD_S03_EXACT_READBACK')
        if proof is None:
            return _hold('HOLD_FACT_EXACT_READBACK_NOT_VERIFIED',409)
        return JSONResponse(proof,headers={
            'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

