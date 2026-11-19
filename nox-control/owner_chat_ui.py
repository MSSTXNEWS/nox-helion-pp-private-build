"""Activate the existing graphical Resonance for authenticated NOX owners."""
from __future__ import annotations
import asyncio,json,os,re,stat,time
import importlib.util
from pathlib import Path
from fastapi import Request
from fastapi.responses import JSONResponse,RedirectResponse
from fastapi.routing import APIRoute

ROOT=Path('/root/nox')
DEST='/nox-web-v29/pc/resonance.html'
PAGES={'pc/resonance.html','pc/v22/resonance.template.html'}
BUILD='NOX_OWNER_LIVE_RESONANCE_20261116'
WORK_PROGRESS_DIRECTORY=ROOT/'nox-control'/'four_queue_20261118'
WORK_PROGRESS_MODULE=ROOT/'nox-control'/'complete_executor_20261118'/'source_baseline'/'work_progress.py'

def decorate_html(raw,path):
    if path.lstrip('/') not in PAGES:return raw
    if raw.count('</head>')!=1:raise ValueError('HOLD_RESONANCE_HEAD')
    # The original archive assumes hosting at /. Our owner-only mount is nested.
    raw=raw.replace('="/pc/','="/nox-web-v29/pc/').replace("='/pc/","='/nox-web-v29/pc/")
    # The legacy shell otherwise inserts a second, unmounted /pc/v25 CSS URL.
    # Mark only its exact, already relocated stylesheet; preserve the asset.
    def shell_css(match):
        tag=match.group(0)
        if (re.search(r'\bhref\s*=\s*([\"\'])/nox-web-v29/pc/v25/nox-shell-v25\.css(?:\?[^\"\']*)?\1',tag,re.I)
                and not re.search(r'\bdata-n25-css(?:\s*=|\s|/?>)',tag,re.I)):
            end='/>' if tag.endswith('/>') else '>'
            return tag[:-len(end)]+' data-n25-css="1"'+end
        return tag
    raw=re.sub(r'<link\b[^>]*>',shell_css,raw,flags=re.I)
    # A single stale marker does not prove that all live owner handlers exist.
    # Check each actual script tag: preserve already-mounted scripts and restore
    # only missing pieces. This is idempotent for partially decorated archives.
    # Comments in retained archives are not live <meta> or <script> elements.
    # Inspect a non-comment view but preserve the exact original HTML bytes.
    active_markup=re.sub(r'<!--.*?(?:-->|$)', '', raw, flags=re.S)
    extra=''
    if not re.search(r'<meta\b[^>]*\bname\s*=\s*(["\'])nox-live-build\1',active_markup,re.I):
        extra='\n<meta name="nox-live-build" content="'+BUILD+'">\n'
    for name in ('nox-v135-resonance-owner-bridge.js','nox-v137-owner-self-status.js','owner-chat-ui.js','owner-presence.js'):
        if re.search(r'<script\b[^>]*\bsrc\s*=\s*(["\'])/nox-web-v29/'
                     +re.escape(name)+r'(?:\?[^"\']*)?\1',active_markup,re.I):
            continue
        extra+='<script defer src="/nox-web-v29/'+name+'" data-nox-live-owner="1"></script>\n'
    return raw.replace('</head>',extra+'</head>',1) if extra else raw

def owner_maintenance_gate():
    """Read-only, fail-closed owner maintenance indicator; never grants a lease."""
    parent = ROOT / 'state'
    # A missing/unreadable state directory is UNKNOWN, not an absent owner STOP.
    # Anchor the marker lookup to one non-symlink directory FD.
    try:
        fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return 'UNKNOWN'
    try:
        opened = os.fstat(fd)
        if not stat.S_ISDIR(opened.st_mode):
            return 'UNKNOWN'
        try:
            flag = os.stat('OWNER_MAINTENANCE.flag', dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            status = 'ABSENT'
        except OSError:
            return 'UNKNOWN'
        else:
            status = 'PRESENT' if stat.S_ISREG(flag.st_mode) else 'UNKNOWN'
        # A swapped directory must not be classified using stale evidence.
        try:
            current = parent.lstat()
        except OSError:
            return 'UNKNOWN'
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            return 'UNKNOWN'
        return status
    finally:
        os.close(fd)


def workers():
    """Read a single bounded descriptor-pinned worker snapshot, fail closed on races."""
    result={'schema':'NOX_OWNER_EXECUTORS_V1','state':'UNAVAILABLE','workers':[],
            'configured':None,'observed_at':None,'training_held':(ROOT/'state/TRAIN_HOLD.flag').exists()}
    maintenance=owner_maintenance_gate()
    result['owner_maintenance']=maintenance
    if maintenance!='ABSENT':
        result['state']='MODEL_UPDATE' if maintenance=='PRESENT' else 'HOLD_MAINTENANCE_UNKNOWN'
        return result
    try:
        directory=ROOT/'status'
        parent_fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            anchor=os.fstat(parent_fd)
            file_fd=os.open('agents_t856u.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent_fd)
            try:
                before=os.fstat(file_fd)
                if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=750000:return result
                raw=os.read(file_fd,750001)
                after=os.fstat(file_fd)
                if len(raw)!=before.st_size or (
                    before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns
                )!=(
                    after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns
                ):return result
            finally:
                os.close(file_fd)
            current=directory.lstat()
            if not stat.S_ISDIR(current.st_mode) or (
                current.st_dev,current.st_ino
            )!=(anchor.st_dev,anchor.st_ino):return result
        finally:
            os.close(parent_fd)
        value=json.loads(raw)
        stamp=before.st_mtime
        if not isinstance(value,dict):return result
        rows=value.get('workers')
        if (not isinstance(rows,list) or not 1<=len(rows)<=64 or type(value.get('n')) is not int
                or value['n']!=len(rows)):return result
        if any(not isinstance(row,dict) or not isinstance(row.get('id'),str)
               or not re.fullmatch(r'nox-agent-[0-9]{2}',row['id'])
               or row.get('status') not in ('idle','busy') for row in rows):return result
        if len({row['id'] for row in rows})!=len(rows):return result
        claims=[row.get('current_task',{}).get('id') for row in rows if isinstance(row.get('current_task'),dict)]
        if (any(not isinstance(claim,str) or not claim.strip() or len(claim)>100 for claim in claims)
                or len(set(claims))!=len(claims)):return result
        if any((row['status']=='busy')!=isinstance(row.get('current_task'),dict) for row in rows):return result
        # A maintenance transition during snapshot reading invalidates even valid data.
        maintenance=owner_maintenance_gate()
        if maintenance!='ABSENT':
            result['owner_maintenance']=maintenance
            result['state']='MODEL_UPDATE' if maintenance=='PRESENT' else 'HOLD_MAINTENANCE_UNKNOWN'
            return result
        for row in rows:
            task=row.get('current_task')
            result['workers'].append({'id':str(row.get('id',''))[:60],
                'status':str(row.get('status','unknown'))[:30],
                'task_id':str(task.get('id',''))[:100] if isinstance(task,dict) else None})
        result.update(state='OBSERVED' if -5<=time.time()-stamp<=45 else 'STALE',
                      configured=value.get('n'),observed_at=stamp)
    except (OSError,ValueError,TypeError):pass
    return result

def work_progress_snapshot():
    """Read the frozen rollup without changing receipts or asserting installation."""
    unavailable={'schema':'NOX_OWNER_WORK_PROGRESS_V1','state':'UNAVAILABLE',
                 'frozen_295_count':295,'receipt_done_count':None,
                 'supplemental_accepted_count':None,'supplemental_accepted_task_ids':[],
                 'receipt_groups':[],'supplemental_state':'UNAVAILABLE',
                 'original_acceptance_added':0,
                 'evidence_scope':'RECEIPTS_AND_APPEND_ONLY_SUPPLEMENTAL_EVIDENCE',
                 'observed_at':time.time()}
    try:
        spec=importlib.util.spec_from_file_location(
            '_nox_owner_work_progress_reader',str(WORK_PROGRESS_MODULE))
        if spec is None or spec.loader is None:return unavailable
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        value=module.summarize(WORK_PROGRESS_DIRECTORY)
        total=value.get('total') if isinstance(value,dict) else None
        supplemental=value.get('supplemental_acceptance') if isinstance(value,dict) else None
        receipt_done=value.get('existing_receipt_count') if isinstance(value,dict) else None
        ids=value.get('supplemental_accepted_task_ids') if isinstance(value,dict) else None
        count=value.get('supplemental_accepted_count') if isinstance(value,dict) else None
        group_rows=value.get('groups') if isinstance(value,dict) else None
        if (value.get('schema')!='nox-work-progress-v2'
                or value.get('frozen_295_count')!=295
                or not isinstance(total,dict)
                or total.get('registered')!=295
                or total.get('total')!=295
                or type(receipt_done) is not int or not 0<=receipt_done<=295
                or type(total.get('completed')) is not int
                or total['completed']!=receipt_done
                or not isinstance(ids,list)
                or any(not isinstance(task_id,str) or len(task_id)>32 for task_id in ids)
                or ids!=sorted(set(ids))
                or type(count) is not int or count!=len(ids)
                or value.get('original_acceptance_added')!=0
                or not isinstance(supplemental,dict)
                or not isinstance(group_rows,list) or len(group_rows)!=7):
            return unavailable
        receipt_groups=[]
        for row in group_rows:
            if (not isinstance(row,dict) or not isinstance(row.get('label'),str)
                    or not row['label'] or len(row['label'])>80
                    or type(row.get('completed')) is not int
                    or type(row.get('total')) is not int
                    or not 0<=row['completed']<=row['total']):
                return unavailable
            receipt_groups.append({'label':row['label'],'done':row['completed'],
                                   'total':row['total']})
        if (sum(row['done'] for row in receipt_groups)!=receipt_done
                or sum(row['total'] for row in receipt_groups)!=295):
            return unavailable
        return {'schema':'NOX_OWNER_WORK_PROGRESS_V1','state':'OBSERVED',
                'frozen_295_count':295,'receipt_done_count':receipt_done,
                'receipt_groups':receipt_groups,
                'supplemental_accepted_count':count,
                'supplemental_accepted_task_ids':ids,
                'supplemental_state':supplemental.get('state','UNKNOWN'),
                'original_acceptance_added':0,
                'evidence_scope':'RECEIPTS_AND_APPEND_ONLY_SUPPLEMENTAL_EVIDENCE',
                'observed_at':time.time()}
    except Exception:
        return unavailable


STOP_CONFIG_PREFLIGHT_SCHEMA='NOX_OWNER_STOP_CONFIG_PREFLIGHT_V1'
STOP_CONFIG_PREDICATES=(
    'serverurl_unix_scheme',
    'serverurl_has_no_authority_query_fragment',
    'socket_path_absolute_no_traversal',
    'socket_serverurl_paths_equal',
    'rpc_factory_matches_fixed_allowlist',
    'configured_owner_is_root_root',
    'configured_mode_format_allowed',
    'configured_mode_private',
    'configured_mode_owner_write_set',
    'endpoint_config_predicates_all_pass',
)


def emergency_stop_config_snapshot():
    """Expose only read-only Supervisor config predicates; never dispatch STOP."""
    unavailable={'schema':STOP_CONFIG_PREFLIGHT_SCHEMA,'state':'UNAVAILABLE',
                 'observed_at':time.time(),'config_predicates':{},
                 'endpoint_predicates':{},'read_only':True,
                 'supervisor_rpc_calls':0,'process_signals':0,'host_writes':0,
                 'stop_command_sent':False,'live_stop_acceptance_proven':False,
                 'evidence_scope':'CONFIG_PREDICATES_ONLY'}
    try:
        from owner_native_emergency_stop_preflight import inspect_configuration
        value=inspect_configuration()
        config_predicates={
            'config_shape_supported':value.get('config_shape_supported'),
            'config_snapshot_stable':value.get('config_snapshot_stable'),
            'include_glob_matches_fixed_scope':value.get('include_glob_matches_fixed_scope'),
        }
        endpoint=value.get('endpoint')
        if (value.get('state')!='ENDPOINT_PREFLIGHT_READ_ONLY'
                or value.get('read_only') is not True
                or value.get('raw_config_values_included') is not False
                or value.get('credentials_included') is not False
                or value.get('argv_included') is not False
                or value.get('supervisor_rpc_calls')!=0
                or value.get('process_signals')!=0
                or value.get('host_writes')!=0
                or not isinstance(endpoint,dict)
                or any(type(flag) is not bool for flag in config_predicates.values())
                or any(type(endpoint.get(name)) is not bool
                       for name in STOP_CONFIG_PREDICATES)):
            return unavailable
        return {'schema':STOP_CONFIG_PREFLIGHT_SCHEMA,'state':'OBSERVED',
                'observed_at':time.time(),'config_predicates':config_predicates,
                'endpoint_predicates':{name:endpoint[name]
                                       for name in STOP_CONFIG_PREDICATES},
                'read_only':True,'supervisor_rpc_calls':0,'process_signals':0,
                'host_writes':0,'stop_command_sent':False,
                'live_stop_acceptance_proven':False,
                'evidence_scope':'CONFIG_PREDICATES_ONLY'}
    except Exception as exc:
        hold=str(exc)
        if re.fullmatch(r'HOLD_ENDPOINT_PREFLIGHT_[A-Z0-9_]+',hold):
            unavailable['state']='HOLD'
            unavailable['hold_reason']=hold
        return unavailable


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
    @app.get('/api/ui/work-progress')
    async def owner_work_progress(request:Request):
        if not check(request):return reject()
        return JSONResponse(await asyncio.to_thread(work_progress_snapshot),
                            headers={'Cache-Control':'no-store'})
    @app.get('/api/ui/emergency-stop-config')
    async def owner_emergency_stop_config(request:Request):
        if not check(request):return reject()
        return JSONResponse(await asyncio.to_thread(emergency_stop_config_snapshot),
                            headers={'Cache-Control':'no-store'})
    return {'home':DEST,'build':BUILD,'authentication':'EXISTING_OWNER_SESSION'}
