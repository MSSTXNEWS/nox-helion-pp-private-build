#!/usr/bin/env python3
"""Pinned owner chat repair in the existing proxy, with bounded rollback."""
from __future__ import annotations
import base64,fcntl,hashlib,json,os,re,shlex,socket,subprocess,sys,time,types,urllib.request
from pathlib import Path

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');SCRIPTS=ROOT/'scripts';STATE=ROOT/'state'
SITE=ROOT/'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
PROXY=SCRIPTS/'chat_proxy.py';BRIDGE=SCRIPTS/'nox_v29_chat_bridge.py'
BRIDGE_SHA='2c714c7f952be64a2b278c993da9d59014a43a32075281b5aa755ada02c6fb8e'
RESONANCE_SHA='9a5ee14787f4fc529926576339f86e07ce6ec838fe6e34fe6b2523f102719194'
HELPER_SHA='b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0'
PYTHON='/root/nox/venv/bin/python'

def emit(kind,value):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':value},separators=(',',':')),flush=True)
def digest(blob):return hashlib.sha256(blob).hexdigest()
def get_bundle(name):
    blob=base64.b64decode(BUNDLE.get(name,''),validate=True)
    if not blob:raise RuntimeError('HOLD_CHAT_BUNDLE_MISSING_'+name.replace('.','_').upper())
    return blob
def module(name,blob):
    mod=types.ModuleType(name);sys.modules[name]=mod
    exec(compile(blob,'<'+name+'>','exec'),mod.__dict__);return mod
def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1000000:raise RuntimeError('HOLD_CHAT_NATIVE_FILE')
    return path.read_bytes()
def stop_flag():return any((ROOT/name).exists() for name in ('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP'))
def slots_idle():
    with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=4) as response:value=json.loads(response.read(100000))
    return isinstance(value,list) and len(value)==6 and all(isinstance(row,dict) and not row.get('is_processing',row.get('processing',False)) for row in value)
def port_listening(port):
    for name in ('tcp','tcp6'):
        for line in Path('/proc/net/'+name).read_text().splitlines()[1:]:
            fields=line.split()
            if len(fields)>3 and fields[3]=='0A' and int(fields[1].rsplit(':',1)[1],16)==port:return True
    return False

def prepare_sources(patcher):
    if digest(read(BRIDGE))!=BRIDGE_SHA or digest(read(SITE/'pc/resonance.html'))!=RESONANCE_SHA:
        raise RuntimeError('HOLD_CHAT_OR_RESONANCE_SOURCE_CHANGED')
    bridge=get_bundle('native_v29_full_bridge.py').decode()
    if '_next_native_chunk_or_stop' not in bridge or 'def _dialog_context(' not in bridge:
        raise RuntimeError('HOLD_NEW_BRIDGE_CONTRACT')
    anchor='    directory=Path(site_dir) if site_dir is not None else SITE\n'
    hook='    from nox_v125_live_readonly import register_nox_v125_live_readonly\n    register_nox_v125_live_readonly(app,trusted)\n'
    if 'register_nox_v125_live_readonly(app,trusted)' not in bridge:
        if bridge.count(anchor)!=1:raise RuntimeError('HOLD_V125_PRESERVATION_ANCHOR')
        bridge=bridge.replace(anchor,hook+anchor,1)
    target='        return HTMLResponse(injected, headers={'
    if bridge.count(target)!=1:raise RuntimeError('HOLD_OWNER_STATIC_HTML_ANCHOR')
    bridge=bridge.replace(target,'        from owner_chat_ui import decorate_html\n        injected=decorate_html(injected,path)\n'+target,1)
    proxy=patcher.patch_proxy(read(PROXY)).decode()
    anchor='if __name__ == "__main__":\n    main()'
    if proxy.count(anchor)!=1:raise RuntimeError('HOLD_PROXY_MAIN_ANCHOR')
    registration=('from owner_chat_ui import register_owner_chat_ui\nregister_owner_chat_ui(app,globals())\n'
        'from owner_event_outbox import register_owner_events\nregister_owner_events(app,globals())\n'
        'from owner_media_runtime import register_media\nregister_media(app,globals())\n'
        'from nox_v137_owner_self_observation import register_nox_v137_self_observation\n'
        'register_nox_v137_self_observation(app,globals())\n\n')
    proxy=proxy.replace(anchor,registration+anchor,1)
    observer=get_bundle('owner_self_observation.py').decode()
    observer=observer.replace("        if rc != 0:\n            raise RuntimeError(\"HOLD_SUPERVISOR_READ\")",
        "        if rc not in (0,3):\n            raise RuntimeError(\"HOLD_SUPERVISOR_READ\")",1)
    sources={PROXY:proxy.encode(),BRIDGE:bridge.encode(),
        SCRIPTS/'agent_loop.py':patcher.patch_agent_loop(read(SCRIPTS/'agent_loop.py')),
        SCRIPTS/'slim_chat_t885u.py':patcher.patch_slim(read(SCRIPTS/'slim_chat_t885u.py')),
        SCRIPTS/'owner_chat_stream.py':get_bundle('owner_chat_stream.py'),
        SCRIPTS/'owner_chat_ui.py':get_bundle('owner_chat_ui.py'),
        SCRIPTS/'owner_event_outbox.py':get_bundle('owner_event_outbox.py'),
        SCRIPTS/'owner_media_runtime.py':get_bundle('owner_media_runtime.py'),
        SCRIPTS/'nox_v137_owner_self_observation.py':observer.encode(),
        SITE/'nox-v135-resonance-owner-bridge.js':get_bundle('nox-v135-resonance-owner-bridge.js'),
        SITE/'nox-v137-owner-self-status.js':get_bundle('nox-v137-owner-self-status.js'),
        SITE/'owner-chat-ui.js':get_bundle('owner-chat-ui.js'),
        SITE/'owner-presence.js':get_bundle('owner-presence.js')}
    for path,blob in sources.items():
        if path.suffix=='.py':compile(blob,str(path),'exec')
    return sources

def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):raise RuntimeError('HOLD_OWNER_CONTEXT')
    raw=get_bundle('owner_native_repair.py')
    if digest(raw)!=HELPER_SHA:raise RuntimeError('HOLD_CHAT_REVIEWED_HELPER')
    helper=module('owner_chat_deploy_helpers',raw)
    patcher=module('owner_chat_source_patch',get_bundle('owner_chat_source_patch.py'))
    receipt=STATE/('owner_chat_upgrade_'+request+'.json');backup=ROOT/'backup/owner_chat_upgrade'/request
    if receipt.exists():raise RuntimeError('HOLD_CHAT_REQUEST_ALREADY_STARTED')
    fd=os.open(STATE/'owner_maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    record={'schema':'NOX_OWNER_CHAT_UPGRADE_V1','request':request,'source_sha':source,'started':time.time(),
        'model_restarted':False,'weights_deleted':0,'chat_restarted':False,'steps':[]}
    old={};installed=[];stopped=False;changed=False;okay=False
    def save():helper.atomic(receipt,json.dumps(record,indent=2).encode())
    def event(kind,data):record['steps'].append({'kind':kind,'data':data,'at':time.time()});save();emit(kind,data)
    def start_proxy():
        if port_listening(8080):raise RuntimeError('HOLD_PROXY_PORT_OCCUPIED_BEFORE_START')
        rc,_=helper.command(['supervisorctl','start','nox-proxy'],35)
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            if helper.service_state('nox-proxy')['state']=='RUNNING' and helper.health().get('8080')==200:return
            time.sleep(1)
        raise RuntimeError('HOLD_PROXY_RESTART_HEALTH')
    try:
        save()
        if stop_flag():raise RuntimeError('HOLD_GLOBAL_STOP')
        sources=prepare_sources(patcher)
        service=helper.service_state('nox-proxy');row=helper.process(service.get('pid')) if service.get('pid') else None
        if service['state']!='RUNNING' or not row or row.get('service')!='nox-proxy' or str(PROXY) not in row['argv']:
            raise RuntimeError('HOLD_EXISTING_PROXY_IDENTITY')
        config=helper.program_config('nox-proxy')
        if '/opt/supervisor-scripts/nox-proxy.sh' not in shlex.split(config.get('command','')):raise RuntimeError('HOLD_PROXY_WRAPPER_IDENTITY')
        if config.get('stopasgroup')=='true' or config.get('killasgroup')=='true':
            if any(x['service']!='nox-proxy' for x in helper.process_table().values() if x['pgrp']==row['pgrp'] and x['state']!='Z'):
                raise RuntimeError('HOLD_PROXY_FOREIGN_PROCESS_GROUP')
        deadline=time.monotonic()+45
        while not slots_idle() and time.monotonic()<deadline:time.sleep(1)
        if not slots_idle():raise RuntimeError('HOLD_LIVE_OWNER_GENERATION')
        for path,blob in sources.items():
            if path.is_symlink():raise RuntimeError('HOLD_CHAT_TARGET_SYMLINK')
            if path.exists():
                old[path]=read(path);helper.atomic(backup/str(path).lstrip('/'),old[path])
            else:old[path]=None
        event('chat_preflight',{'proxy_pid':service['pid'],'model_slots_idle':True,'files':len(sources),
                                'old_bridge_sha256':BRIDGE_SHA,'old_proxy_sha256':patcher.PROXY_SHA})
        rc,_=helper.command(['supervisorctl','stop','nox-proxy'],45)
        stopped=helper.service_state('nox-proxy')['state'] in ('STOPPED','EXITED')
        if not stopped or port_listening(8080):raise RuntimeError('HOLD_PROXY_STOP_NOT_VERIFIED')
        for path,blob in sources.items():
            helper.atomic(path,blob);os.chmod(path,0o644);installed.append(path);changed=True
        # Import/syntax smoke in the SAME interpreter before accepting a restart.
        smoke="import sys;sys.path.insert(0,'/root/nox/scripts');import chat_proxy;assert any(getattr(r,'path','')=='/api/ui/media/jobs' for r in chat_proxy.app.routes)"
        result=subprocess.run([PYTHON,'-c',smoke],capture_output=True,timeout=45)
        if result.returncode:raise RuntimeError('HOLD_CHAT_IMPORT_SMOKE')
        start_proxy();stopped=False;record['chat_restarted']=True
        event('chat_sources_installed',[{'path':str(path),'sha256':digest(blob)} for path,blob in sources.items()])
        # Release task admission while the independent owner dialog test runs.
        fcntl.flock(fd,fcntl.LOCK_UN)
        test=get_bundle('owner_chat_probe.py')
        env=dict(os.environ,NOX_PROBE_NONLOOPBACK='1',NOX_PROBE_SECOND_TURN='1',NOX_PROBE_SOURCE_EXPORT='0')
        result=subprocess.run([PYTHON,'-'],input=test,capture_output=True,timeout=270,env=env)
        evidence=[]
        for line in result.stdout.decode(errors='replace').splitlines():
            if line.startswith('NOX_MAINT_REPAIR='):
                value=json.loads(line.split('=',1)[1]);evidence.append(value)
                if value.get('kind') not in ('chat_source','chat_asset'):print(line,flush=True)
        record['acceptance']=evidence
        answers=[x['data'] for x in evidence if x.get('kind')=='chat_synthetic_latency']
        history=[x['data'] for x in evidence if x.get('kind')=='chat_history_followup']
        routing=[x['data'] for x in evidence if x.get('kind')=='chat_before_probe']
        executors=[x['data'] for x in evidence if x.get('kind')=='chat_executor_question']
        if (result.returncode or len(answers)!=1 or not answers[0].get('saved_verified') or not answers[0].get('arithmetic_pass')
                or len(history)!=1 or not history[0].get('history_model_pass') or not routing
                or routing[0].get('nonloopback_peer') is not True or routing[0].get('owner_status_bound') is not True
                or routing[0].get('owner_executors_access') is not True
                or not routing[0].get('assets') or any(x.get('status')!=200 for x in routing[0]['assets'])
                or set(routing[0].get('anonymous_http',{}).values())!={401}
                or len(executors)!=1 or executors[0].get('verified_six_plus_nox') is not True
                or any(x['final_path']!='/nox-web-v29/pc/resonance.html' for x in routing[0]['paths'] if x['path'] in ('/','/chat'))):
            raise RuntimeError('HOLD_CHAT_NATIVE_ACCEPTANCE')
        record['performance_targets_passed']=bool(answers[0].get('performance_target_pass') is True and history[0].get('performance_target_pass') is True)
        record['state']=('LIVE_RESONANCE_REAL_STREAM_S03_HISTORY_ACCEPTED' if record['performance_targets_passed']
                         else 'LIVE_RESONANCE_FUNCTIONAL_PERFORMANCE_PENDING')
        okay=True
    except Exception as exc:
        reason=str(exc);record['state']='HOLD_CHAT_UPGRADE';record['error']=reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__
        if changed:
            try:
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                if helper.service_state('nox-proxy')['state']=='RUNNING':helper.command(['supervisorctl','stop','nox-proxy'],45)
                for path in installed:
                    if old[path] is not None:helper.atomic(path,old[path]);os.chmod(path,0o644)
                    # Added inert modules/assets may remain; no deletion or user data loss.
                start_proxy();stopped=False;record['rollback_verified']=helper.health().get('8080')==200
            except Exception as rollback:record['rollback_verified']=False;record['rollback_error']=type(rollback).__name__
        elif stopped:
            try:start_proxy();stopped=False
            except Exception:record['rollback_verified']=False
    finally:
        record.update(finished=time.time(),health_after=helper.health(),proxy_after=helper.service_state('nox-proxy'))
        save();emit('chat_upgrade_receipt',record);os.close(fd)
    if okay:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0 if okay else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        reason=str(exc);emit('chat_upgrade_failure',reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__);raise SystemExit(2)
