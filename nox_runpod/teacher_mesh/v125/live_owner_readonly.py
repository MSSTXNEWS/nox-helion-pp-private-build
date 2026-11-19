"""V125: authentic, owner-only status and process telemetry on EXISTING OneHost.

No new server, model, database, Windows PC sensor assertions or fake training.
All readings come from /proc, nvidia-smi, supervisor and existing S03 only.
"""
from __future__ import annotations
import asyncio
from datetime import datetime,timezone
import hashlib
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

_SMI=("nvidia-smi","--query-gpu=index,utilization.gpu,memory.total,memory.used,temperature.gpu",
      "--format=csv,noheader,nounits")
_WEB=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site')
_ROUTES=('/api/status','/api/nox/system/processes',
         '/api/nox/premium/status','/api/nox/premium/capabilities',
         '/api/nox/training/status')


def _stat(raw):
    lines=raw.splitlines()
    if not lines or not lines[0].startswith('cpu '):
        raise RuntimeError('HOLD_PROCFS_CPU_SOURCE')
    try:
        numbers=[int(x) for x in lines[0].split()[1:]]
    except ValueError as exc:
        raise RuntimeError('HOLD_PROCFS_CPU_FORMAT') from exc
    if len(numbers)<5 or any(x<0 for x in numbers):
        raise RuntimeError('HOLD_PROCFS_CPU_FIELDS')
    return sum(numbers),numbers[3]+numbers[4]


def _mem(raw):
    out={}
    for line in raw.splitlines():
        match=re.match(r'^(MemTotal|MemAvailable):\s*(\d+)\s+kB$',line)
        if match:
            out[match.group(1)]=int(match.group(2))
    total=out.get('MemTotal',0)
    available=out.get('MemAvailable',-1)
    if total<1048576 or not 0<=available<=total:
        raise RuntimeError('HOLD_PROCFS_MEM_SOURCE')
    return {'total_gib':total/1048576,'used_gib':(total-available)/1048576,
            'percent':100*(total-available)/total}


def _gpu_rows(raw):
    result=[]
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            values=[int(p.strip()) for p in line.split(',')]
        except ValueError as exc:
            raise RuntimeError('HOLD_GPU_SAMPLE_FORMAT') from exc
        if len(values)!=5:
            raise RuntimeError('HOLD_GPU_SAMPLE_FORMAT')
        idx,util,total,used,temp=values
        if (idx<0 or not 0<=util<=100 or total<=0 or
                not 0<=used<=total or not -20<=temp<=150):
            raise RuntimeError('HOLD_GPU_SAMPLE_RANGE')
        result.append({'index':idx,'gpu_percent':util,
                       'vram_total_gib':total/1024,'vram_used_gib':used/1024,
                       'gpu_core_temp_c':temp})
    if not result or len(result)>8 or len({g['index'] for g in result})!=len(result):
        raise RuntimeError('HOLD_GPU_SAMPLE_COUNT')
    return result


def _status():
    before=_stat(Path('/proc/stat').read_text(encoding='ascii'))
    time.sleep(0.10)
    after=_stat(Path('/proc/stat').read_text(encoding='ascii'))
    total=after[0]-before[0]
    idle=after[1]-before[1]
    if total<=0 or not 0<=idle<=total:
        raise RuntimeError('HOLD_CPU_DIFFERENCE')
    cpu=100*(total-idle)/total
    memory=_mem(Path('/proc/meminfo').read_text(encoding='ascii'))
    smi=subprocess.run(_SMI,capture_output=True,text=True,timeout=7,check=False)
    if smi.returncode!=0 or len(smi.stdout)>5000:
        raise RuntimeError('HOLD_NATIVE_NVIDIA_SMI')
    gpu=_gpu_rows(smi.stdout)
    now=time.time()
    gpu_peak=max(g['gpu_percent'] for g in gpu)
    vram_total=sum(g['vram_total_gib'] for g in gpu)
    vram_used=sum(g['vram_used_gib'] for g in gpu)
    core_temp=max(g['gpu_core_temp_c'] for g in gpu)
    return {
        'status':'READY','source':'NOX_VAST_PROCFS_NVIDIA_SMI',
        'scope':'VAST_ONEHOST_SERVER_NOT_OWNER_WINDOWS_PC',
        'physical_windows_pc_verified':False,'sampled_at':now,
        'timestamp':now,'timestamp_utc':datetime.fromtimestamp(now,timezone.utc).isoformat(),
        'stale':False,'read_only':True,'gpu_sensor_source':'GPU NVIDIA-SMI',
        'sensor_source':'GPU NVIDIA-SMI','gpu_core_temp':core_temp,
        'gpu_temp':None,'gpu_hotspot_c':None,'cpu_temp':None,
        'cpu_percent':round(cpu,3),'gpu_percent':gpu_peak,
        'ram_percent':round(memory['percent'],3),
        'ram_used_gb':round(memory['used_gib'],4),
        'ram_total_gb':round(memory['total_gib'],4),
        'vram_used_gb':round(vram_used,4),'vram_total_gb':round(vram_total,4),
        'system':{'cpu_usage_pct':round(cpu,3),
                  'ram_usage_pct':round(memory['percent'],3),
                  'ram_used_gib':round(memory['used_gib'],4),
                  'ram_total_gib':round(memory['total_gib'],4),
                  'data_source':'PROCFS'},
        'load':{'gpu_load_pct':gpu_peak,'gpu_memory_used_gib':round(vram_used,4),
                'gpu_memory_total_gib':round(vram_total,4),
                'data_source':'GPU NVIDIA-SMI'},
        'gpus':gpu}


def _processes():
    count=0
    category_counts={'python':0,'llama':0,'supervisor':0,'node':0}
    for child in Path('/proc').iterdir():
        if not child.name.isdecimal():
            continue
        count+=1
        try:
            value=(child/'comm').read_text(encoding='ascii').strip().lower()
        except (OSError,UnicodeError):
            continue
        if len(value)>40:
            continue
        for name,part in (('python','python'),('llama','llama'),
                          ('supervisor','supervis'),('node','node')):
            if part in value:
                category_counts[name]+=1
    if count==0:
        raise RuntimeError('HOLD_NATIVE_PROCFS_EMPTY')
    return {'status':'READY','source':'PROCFS','sampled_at':time.time(),
            'read_only':True,'stale':False,'observed_count':count,
            'categories':category_counts,'pid_arguments_exported':False,
            'scope':'VAST_ONEHOST_SERVER_NOT_OWNER_WINDOWS_PC'}


def _asset_sha():
    path=_WEB/'ASSET-MANIFEST-V17.json'
    if not path.is_file() or path.is_symlink() or path.stat().st_size>1000000:
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _s03_schema_ready():
    try:
        import s03_memory
        path=Path(s03_memory.DB)
        if not path.is_file() or path.is_symlink():
            return False
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=3) as db:
            db.execute('PRAGMA query_only=ON')
            tables={r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        return {'s03_items','nox_v29_dialogs','nox_v29_dialog_messages'} <= tables
    except (sqlite3.Error,RuntimeError,ImportError,OSError,ValueError):
        return False


def _owner_status():
    return {'status':'READY','owner':'EXISTING_NATIVE_ONEHOST',
            'authentication':'EXISTING_HTTPONLY_OWNER_COOKIE',
            'separate_backend':False,'asset_manifest_sha256':_asset_sha(),
            'asset_manifest_verified':_asset_sha() is not None,
            'scope':'VAST_ONEHOST_SERVER_NOT_OWNER_WINDOWS_PC',
            'training_verified_by_status':False}


def _capabilities(app):
    active={r.path for r in app.routes if isinstance(r,APIRoute)}
    ready=_s03_schema_ready()
    return {'schema':'NOX_NATIVE_CONTROLLER_V2','status':'READY',
            'owner':'EXISTING_NATIVE_ONEHOST',
            'authentication':'EXISTING_HTTPONLY_OWNER_COOKIE',
            'separate_backend':False,'source':'LIVE_ONEHOST_REGISTERED_ROUTES',
            'features':{
                'memory':{'available':ready,'reason':None if ready else 'S03_SCHEMA_UNVERIFIED'},
                'system':{'available':True,'read_only':True,'source':'PROCFS'},
                'training':{'full_weight_optimizer_verified':False,
                            'reason':'CHECKPOINT_NOT_VERIFIED'},
                'voice':{'available':False,'reason':'VOICE_NATIVE_NOT_VERIFIED'},
                'push':{'available':False,'reason':'PUSH_NATIVE_NOT_VERIFIED'},
                'install':{'available':False,'reason':'WINDOWS_INSTALLER_NOT_VERIFIED'},
                'services':{'available':False,'reason':'EXTERNAL_SERVICES_NOT_VERIFIED'}},
            'native_routes_checked':len(active),
            'physical_windows_pc_verified':False,
            'all_web_features_verified':False}


def _trainer():
    try:
        from nox_v118_real_read_surfaces import _training_state
    except ImportError as exc:
        raise RuntimeError('HOLD_NATIVE_TRAINER_ADAPTER') from exc
    value=_training_state()
    if not isinstance(value,dict):
        raise RuntimeError('HOLD_TRAINER_READ')
    value={**value,'native_owner':True,'source':'NOX_ORIGINAL_SUPERVISOR_READ_ONLY',
           'training_binding_verified':False,'verified_live':False}
    return value


def register_nox_v125_live_readonly(app,trusted):
    session=trusted.get('_session_ok')
    unauthorized=trusted.get('_unauthorized')
    if not callable(session) or not callable(unauthorized):
        raise RuntimeError('HOLD_TRUSTED_COOKIE_SESSION_REQUIRED')
    existing={getattr(r,'path','') for r in app.routes}
    if any(p in existing for p in _ROUTES):
        raise RuntimeError('HOLD_V125_CONFLICT_EXISTING_ENDPOINT')
    async def serve(request,fn):
        if not session(request):
            return unauthorized()
        try:
            data=await asyncio.wait_for(asyncio.to_thread(fn),timeout=9)
            return JSONResponse(data,headers={'Cache-Control':'no-store',
                                              'X-Content-Type-Options':'nosniff'})
        except Exception as exc:
            reason=str(exc)
            reason=reason if reason.startswith('HOLD_') and len(reason)<100 else 'HOLD_NATIVE_TELEMETRY'
            return JSONResponse({'status':'HOLD','reason':reason},status_code=503,
                                headers={'Cache-Control':'no-store'})
    @app.get('/api/status')
    async def owner_metrics(request:Request):
        return await serve(request,_status)
    @app.get('/api/nox/system/processes')
    async def owner_processes(request:Request):
        return await serve(request,_processes)
    @app.get('/api/nox/premium/status')
    async def owner_premium_status(request:Request):
        return await serve(request,_owner_status)
    @app.get('/api/nox/premium/capabilities')
    async def owner_premium_capabilities(request:Request):
        return await serve(request,lambda:_capabilities(app))
    @app.get('/api/nox/training/status')
    async def owner_training_status(request:Request):
        return await serve(request,_trainer)
