"""V118: genuine, owner-only read surfaces from existing NOX OneHost.
No new daemon, trainer, LLM, database, fake model progress or shell endpoints.
Never present remote Vast metrics as user Windows PC telemetry.
"""
from __future__ import annotations
import asyncio
import json
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse

def _local_json(port:int,path:str,limit:int=30000):
    with urllib.request.urlopen(
        urllib.request.Request(f'http://127.0.0.1:{port}{path}',method='GET'),
        timeout=3) as r:
        if r.status!=200:raise RuntimeError('HOLD_UPSTREAM_HTTP')
        data=r.read(limit+1)
        if len(data)>limit:raise RuntimeError('HOLD_UPSTREAM_LIMIT')
        return json.loads(data)

def _s03_stats():
    import s03_memory
    path=Path(s03_memory.DB)
    if not path.is_file() or path.is_symlink():raise RuntimeError('HOLD_ORIGINAL_S03_MISSING')
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=3) as con:
        con.execute('PRAGMA query_only=ON')
        check=con.execute('PRAGMA quick_check').fetchone()[0]
        if check!='ok':raise RuntimeError('HOLD_S03_INTEGRITY')
        cols={r[1] for r in con.execute('PRAGMA table_info(s03_items)')}
        if 'id' not in cols and not cols:raise RuntimeError('HOLD_S03_SCHEMA')
        total=con.execute('SELECT COUNT(*) FROM s03_items').fetchone()[0]
        segment='segment' if 'segment' in cols else 'level' if 'level' in cols else None
        rows={}
        if segment:
            for key,num in con.execute('SELECT "'+segment+'",COUNT(*) FROM s03_items GROUP BY "'+segment+'"'):
                if isinstance(key,str) and 1<=len(key)<=12:
                    rows[key]=num
        return {'status':'READY','backing_store':'EXISTING_S03_SQLITE',
                'original_s03_quick_check':'ok','s03_items_count':total,
                'stats':rows,'source':'NOX_NATIVE_LOCAL_SQLITE',
                'no_private_records_returned':True}

def _training_state():
    try:
        p=subprocess.run(['supervisorctl','status','nox-train-volta-t866u'],
                         capture_output=True,text=True,timeout=5)
        words=p.stdout.split()
        state=words[1] if p.returncode==0 and len(words)>1 else 'UNKNOWN'
    except Exception:state='UNKNOWN'
    return {'status':'HOLD_CHECKPOINT_NOT_VERIFIED','service':'nox-train-volta-t866u',
            'supervisor_state':state,'verified_live':False,
            'full_parameter_no_adapter_verified':False,
            'full_weight_optimizer_steps_verified':None,
            'checkpoint_restore_verified':False,
            'source':'NOX_SUPERVISOR_READ_ONLY'}

def _activity():
    slots=_local_json(8081,'/slots')
    if not isinstance(slots,list) or len(slots)!=6:
        raise RuntimeError('HOLD_PRIMARY_MODEL_SLOTS')
    if not all(isinstance(x,dict) for x in slots):
        raise RuntimeError('HOLD_PRIMARY_MODEL_SLOTS_TYPE')
    count=sum(bool(x.get('is_processing',x.get('processing',False))) for x in slots)
    return {'status':'READY','active_generations':count,'busy':bool(count),
            'source':'ACTUAL_NOX_MODEL_SLOTS','timestamp':time.time(),
            'training_verified_by_this_read':False,
            'phases':{'inference_active':bool(count)}}

def _model():
    data=_local_json(8081,'/v1/models')
    entries=data.get('data') if isinstance(data,dict) else None
    if not isinstance(entries,list) or len(entries)<1:raise RuntimeError('HOLD_MODEL_NOT_LOADED')
    names=[str(x.get('id') or '')[:150] for x in entries if isinstance(x,dict)]
    if not names or not names[0]:raise RuntimeError('HOLD_MODEL_ID')
    return {'status':'READY','backend':'EXISTING_NOX_ONEHOST','model_id':names[0],
            'models':names[:6],'model':'NOX HELION',
            'weights_training_verified':False,'source':'LOCAL_8081_V1_MODELS'}

def _health():
    ports=[]
    for port in (8080,8081):
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as r:
            ports.append(r.status)
    if ports!=[200,200]:raise RuntimeError('HOLD_NOX_HEALTH')
    return {'status':'READY','backend':'EXISTING_NOX_ONEHOST',
            'chat_http':200,'model_http':200,'timestamp':time.time(),
            'source':'NATIVE_HEALTH_PROBES','full_web_accepted':False}

def _hide(reason:str):
    return JSONResponse({'status':'HOLD','reason':reason},status_code=503,
                        headers={'Cache-Control':'no-store'})

def register_nox_v118_real_read_surfaces(app,trusted):
    auth=trusted.get('_session_ok')
    unauthorized=trusted.get('_unauthorized')
    if not callable(auth) or not callable(unauthorized):
        raise RuntimeError('HOLD_EXISTING_OWNER_AUTH')
    target=('/api/health','/api/nox/activity','/api/nox/model',
            '/api/nox/memory','/api/training/status','/api/ui/memory/status')
    existing={getattr(r,'path','') for r in app.routes}
    if any(x in existing for x in target):raise RuntimeError('HOLD_EXISTING_ROUTE_CONFLICT')
    async def secure(request:Request,fn):
        if not auth(request):return unauthorized()
        try:
            data=await asyncio.wait_for(asyncio.to_thread(fn),timeout=7.0)
            return JSONResponse(data,headers={'Cache-Control':'no-store'})
        except Exception as ex:
            reason=str(ex)
            return _hide(reason if reason.startswith('HOLD_') and len(reason)<120 else 'HOLD_NATIVE_DATA_UNAVAILABLE')
    @app.get('/api/health')
    async def health(request:Request):return await secure(request,_health)
    @app.get('/api/nox/activity')
    async def activity(request:Request):return await secure(request,_activity)
    @app.get('/api/nox/model')
    async def model(request:Request):return await secure(request,_model)
    @app.get('/api/nox/memory')
    async def memory(request:Request):return await secure(request,_s03_stats)
    @app.get('/api/training/status')
    async def training(request:Request):return await secure(request,_training_state)
    @app.get('/api/ui/memory/status')
    async def memory_status(request:Request):return await secure(request,_s03_stats)
