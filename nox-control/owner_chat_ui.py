"""Activate the existing graphical Resonance for authenticated NOX owners."""
from __future__ import annotations
import asyncio,json,re,time
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse,RedirectResponse
from fastapi.routing import APIRoute

ROOT=Path('/root/nox')
DEST='/nox-web-v29/pc/resonance.html'
PAGES={'pc/resonance.html','pc/v22/resonance.template.html'}
BUILD='NOX_OWNER_LIVE_RESONANCE_20261116'

def decorate_html(raw,path):
    if path.lstrip('/') not in PAGES:return raw
    if raw.count('</head>')!=1:raise ValueError('HOLD_RESONANCE_HEAD')
    # The original archive assumes hosting at /. Our owner-only mount is nested.
    raw=raw.replace('="/pc/','="/nox-web-v29/pc/').replace("='/pc/","='/nox-web-v29/pc/")
    if 'data-nox-live-owner="1"' in raw:return raw
    extra='\n<meta name="nox-live-build" content="'+BUILD+'">\n'
    for name in ('nox-v135-resonance-owner-bridge.js','nox-v137-owner-self-status.js','owner-chat-ui.js','owner-presence.js'):
        extra+='<script defer src="/nox-web-v29/'+name+'" data-nox-live-owner="1"></script>\n'
    return raw.replace('</head>',extra+'</head>',1)

def workers():
    path=ROOT/'status/agents_t856u.json'
    result={'schema':'NOX_OWNER_EXECUTORS_V1','state':'UNAVAILABLE','workers':[],
            'configured':None,'observed_at':None,'training_held':(ROOT/'state/TRAIN_HOLD.flag').exists()}
    try:
        if path.is_symlink() or path.stat().st_size>750000:return result
        value=json.loads(path.read_text());stamp=path.stat().st_mtime
        rows=value.get('workers')
        if (not isinstance(rows,list) or not 1<=len(rows)<=64 or type(value.get('n')) is not int
                or value['n']!=len(rows)):return result
        if any(not isinstance(row,dict) or not isinstance(row.get('id'),str)
               or not re.fullmatch(r'nox-agent-[0-9]{2}',row['id'])
               or row.get('status') not in ('idle','busy') for row in rows):return result
        if len({row['id'] for row in rows})!=len(rows):return result
        claims=[row.get('current_task',{}).get('id') for row in rows if isinstance(row.get('current_task'),dict)]
        if len(set(claims))!=len(claims):return result
        if any((row['status']=='busy')!=isinstance(row.get('current_task'),dict) for row in rows):return result
        for row in rows:
            if not isinstance(row,dict):continue
            task=row.get('current_task')
            result['workers'].append({'id':str(row.get('id',''))[:60],
                'status':str(row.get('status','unknown'))[:30],
                'task_id':str(task.get('id',''))[:100] if isinstance(task,dict) else None})
        result.update(state='OBSERVED' if -5<=time.time()-stamp<=45 else 'STALE',configured=value.get('n'),observed_at=stamp)
    except (OSError,ValueError,TypeError):pass
    return result

def register_owner_chat_ui(app,trusted):
    check=trusted.get('_session_ok');reject=trusted.get('_unauthorized');legacy=trusted.get('chat_page')
    if not all(callable(x) for x in (check,reject,legacy)):raise RuntimeError('HOLD_ORIGINAL_CHAT_CALLBACKS')
    app.router.routes[:]=[route for route in app.router.routes if not (
        isinstance(route,APIRoute) and route.path in ('/','/chat') and route.methods=={'GET'})]
    @app.get('/')
    async def owner_home(request:Request):
        return RedirectResponse(DEST if check(request) else '/chat',status_code=302,headers={'Cache-Control':'no-store'})
    @app.get('/chat')
    async def owner_chat(request:Request):
        if check(request):return RedirectResponse(DEST,status_code=302,headers={'Cache-Control':'no-store'})
        return await legacy()
    @app.get('/api/ui/executors')
    async def owner_executors(request:Request):
        if not check(request):return reject()
        return JSONResponse(await asyncio.to_thread(workers),headers={'Cache-Control':'no-store'})
    @app.get('/api/ui/downloads')
    async def owner_downloads(request:Request):
        if not check(request):return reject()
        from owner_download_status import snapshot
        return JSONResponse(await asyncio.to_thread(snapshot),headers={'Cache-Control':'no-store'})
    return {'home':DEST,'build':BUILD,'authentication':'EXISTING_OWNER_SESSION'}
