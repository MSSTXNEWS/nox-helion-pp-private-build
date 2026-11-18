#!/usr/bin/env python3
"""Explicit owner-command transport; one authenticated SSH session, pinned source.
No push/PR activation, no secret export, no blind retry of native mutations.
"""
from __future__ import annotations
import argparse, base64, contextlib, hashlib, ipaddress, json, os, re, socket, subprocess, sys, time
from pathlib import Path
REPO='MSSTXNEWS/nox-helion-pp-private-build'
OWNER_ID=340718567
INSTANCE=60509551
PIN='SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'
FILES={'audit':'nox-control/owner_native_audit.py','inspect':'nox-control/owner_native_inspect.py',
       'stage':'nox-control/owner_native_stage.py','repair':'nox-control/owner_qwen_held_media_smoke_entry.py',
       'subagent':'nox-control/owner_subagent_fresh_install_entry.py',
       'lifeline':'nox-control/owner_native_lifeline.py'}
MASTER=None

SCOPED_REPAIR_BUNDLES={
    'nox-control/owner_qwen_held_media_smoke_entry.py':(
        'owner_qwen_held_media_smoke.py','owner_media_acceptance_entry.py',
        'owner_qwen_revision_install.py','owner_native_repair.py','owner_download_status_entry.py'),
    'nox-control/owner_subagent_fresh_install_entry.py':(
        'owner_subagent_hash_recovery_entry.py','owner_subagent_install_entry.py',
        'owner_subagent_dispatcher_fresh.py','owner_autonomy_pool.py','owner_subagent_processes.py',
        'owner_dispatcher_mentor.py','owner_task_lifecycle.py','owner_senior_gateway.py'),
    'nox-control/owner_qwen_transport_install_entry.py':(
        'owner_qwen_revision_install.py','qwen_student_training_entry_revision.py',
        'owner_qwen_transport_revision_install.py','qwen_student_training_entry_transport_candidate.py',
        'owner_qwen_execution_revision.py','owner_qwen_revision_guard.py','owner_qwen_revision_status.py',
        'owner_qwen_revision_media_handoff.py','owner_qwen_revision_media_guard.py',
        'owner_qwen_revision_handback_retry.py','owner_hermes_revision_hydrate.py',
        'owner_download_status_entry.py','owner_native_repair.py','owner_qwen_disk_rearm_entry.py'),
}
SCOPED_REPAIR_EXTRA_PATHS={
    'nox-control/owner_qwen_transport_install_entry.py':(
        'nox-control/owner_qwen_transport_revision_install.py',
        'nox-control/qwen_student_training_entry_transport_candidate.py'),
}
SUBAGENT_BUNDLE_PATHS = (
    'nox-control/owner_subagent_hash_recovery_entry.py',
    'nox-control/owner_subagent_install_entry.py',
    'nox-control/owner_subagent_dispatcher_fresh.py',
    'nox-control/owner_autonomy_pool.py',
    'nox-control/owner_subagent_processes.py',
    'nox-control/owner_dispatcher_mentor.py',
    'nox-control/owner_task_lifecycle.py',
    'nox-control/owner_senior_gateway.py',
)
SUBAGENT_BUNDLE_PINS = {
    'owner_subagent_hash_recovery_entry.py': 'de2371d0f5c92063c122b65ff08d15c43015ca599cff8299f9dcb7886bc95659',
    'owner_subagent_install_entry.py': '9f23ac936d16fc019abf8e2ecb9d8aede919827f4c8f41d629d353903db04e51',
    'owner_subagent_dispatcher_fresh.py': 'f4442c3b0b094c4d3afea19f4455144e1c12a9131d210cfe5c9c25d0ae5ab3a9',
    'owner_autonomy_pool.py': 'c4f0a178d22f47c1e1b2575f6b9c3280165eb0cf13920053c7b427ada3d8f8a9',
    'owner_subagent_processes.py': '8805da8d99c7d5fe38db6c9a100fb86cc052e1c795418fd78284a5cb7a84d276',
    'owner_dispatcher_mentor.py': 'b1143626aee7b74e1e3f8fa39d2035d4e29d0a5ec1882fae6efb8cab46260193',
    'owner_task_lifecycle.py': 'b09e02663f11c30e39a15b44ad2b12271219ec25bf0af9937bdf3a5fcfdebe5e',
    'owner_senior_gateway.py': '1fd1556009ce62fa806bdee0a9a34577d276344e728fe9d94b33f44eb151346e',
}

def repair_bundle_paths(action,entrypoint,paths):
    if action not in ('repair', 'subagent') or entrypoint not in SCOPED_REPAIR_BUNDLES:return paths
    selected=SCOPED_REPAIR_BUNDLES[entrypoint]
    if len(set(selected))!=len(selected):raise RuntimeError('HOLD_SCOPED_BUNDLE_DUPLICATE_ALLOWLIST')
    found={}
    for path in (*paths,*SCOPED_REPAIR_EXTRA_PATHS.get(entrypoint,())):
        name=Path(path).name
        if name not in selected:continue
        if name in found:raise RuntimeError('HOLD_SCOPED_BUNDLE_DUPLICATE_SOURCE')
        found[name]=path
    if set(found)!=set(selected):raise RuntimeError('HOLD_SCOPED_BUNDLE_MISSING_SOURCE')
    result=tuple(found[name] for name in selected)
    if any(not Path(path).is_file() for path in result):raise RuntimeError('HOLD_SCOPED_BUNDLE_MISSING_FILE')
    return result

def subagent_bundle_assets(paths):
    selected = repair_bundle_paths('subagent', FILES['subagent'], paths)
    if {Path(path).name for path in selected} != set(SUBAGENT_BUNDLE_PINS):
        raise RuntimeError('HOLD_SUBAGENT_BUNDLE_SCOPE')
    assets = {}
    for path in selected:
        source = Path(path)
        raw = source.read_bytes()
        name = source.name
        if (not raw or len(raw) > 400000
                or hashlib.sha256(raw).hexdigest() != SUBAGENT_BUNDLE_PINS[name]):
            raise RuntimeError('HOLD_SUBAGENT_BUNDLE_SOURCE_PIN')
        assets[name] = base64.b64encode(raw).decode('ascii')
    return assets

def authorize_event(action):
    e=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_EVENT_NAME')!='issue_comment':raise RuntimeError('HOLD_EVENT_SCOPE')
    c=e.get('comment',{});owner=e.get('repository',{}).get('owner',{})
    if (c.get('user',{}).get('id')!=OWNER_ID or owner.get('id')!=OWNER_ID or c.get('author_association')!='OWNER'
            or e.get('issue',{}).get('number')!=256 or e.get('sender',{}).get('id')!=OWNER_ID):raise RuntimeError('HOLD_OWNER_COMMAND_IDENTITY')
    sha=os.environ.get('NOX_PINNED_SOURCE_SHA','')
    if not re.fullmatch('[0-9a-f]{40}',sha):raise RuntimeError('HOLD_SOURCE_PIN')
    if c.get('body')!=f'/nox-maintain {INSTANCE} {sha} {action}':raise RuntimeError('HOLD_EXACT_OWNER_COMMAND')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise RuntimeError('HOLD_CHECKOUT_MISMATCH')
    return c['id']

def run_native(action,request_id):
    global MASTER
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
    key=os.environ.get('NOX2','')
    if not key:raise RuntimeError('HOLD_OWNER_API_CREDENTIAL_UNAVAILABLE')
    values=s.api('GET','/instances/',key)
    values=values.get('instances',values) if isinstance(values,dict) else values
    target=next((x for x in values if isinstance(x,dict) and str(x.get('id'))==str(INSTANCE)),None) if isinstance(values,list) else None
    def public_state(value):
        return value if isinstance(value,str) and re.fullmatch('[a-zA-Z0-9_-]{1,40}',value) else None
    print('NOX_MAINT_INSTANCE_STATE='+json.dumps({'instance':INSTANCE,'found':target is not None,
        'actual_status':public_state(target.get('actual_status')) if target else None,
        'intended_status':public_state(target.get('intended_status')) if target else None,
        'cur_state':public_state(target.get('cur_state')) if target else None,
        'num_gpus':int(str(target.get('num_gpus'))) if target and re.fullmatch('[0-9]{1,2}',str(target.get('num_gpus'))) else None,
        'read_only_provider_lookup':True,'provider_mutations':0},sort_keys=True),flush=True)
    if not target or target.get('actual_status')!='running' or str(target.get('num_gpus'))!='2':raise RuntimeError('HOLD_EXACT_RUNNING_INSTANCE')
    ip=target.get('public_ipaddr')
    if not ipaddress.ip_address(ip).is_global:raise RuntimeError('HOLD_INSTANCE_ROUTE')
    port=None
    for m in target.get('ports',{}).get('22/tcp',[]):
        value=str(m.get('HostPort',''))
        if not value.isdigit() or not 1<=int(value)<=65535:continue
        try:
            with socket.create_connection((ip,int(value)),timeout=6) as sock:
                sock.settimeout(5)
                if sock.recv(128).startswith(b'SSH-2.0'):port=int(value);break
        except OSError:continue
    if port is None:raise RuntimeError('HOLD_CURRENT_SSH_ROUTE')
    s.RUNNER.mkdir(parents=True,mode=0o700,exist_ok=True)
    known=s.RUNNER/'known_hosts'
    p=subprocess.run(['ssh-keyscan','-T','8','-t','ed25519','-p',str(port),ip],capture_output=True,text=True,timeout=12)
    known.write_text(p.stdout[:8000]);known.chmod(0o600)
    fp=subprocess.run(['ssh-keygen','-lf',str(known),'-E','sha256'],capture_output=True,text=True,timeout=8)
    if p.returncode or fp.returncode or PIN not in fp.stdout:raise RuntimeError('HOLD_OWNER_HOST_PIN')
    print('NOX_MAINT_HOST_PIN=VERIFIED',flush=True)
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','nox-owner-maint-'+os.environ.get('GITHUB_RUN_ID','manual'),'-f',str(s.KEY)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=12)
    s.KEY.chmod(0o600);public=s.KEY.with_suffix('.pub').read_text().strip()
    if not public.startswith('ssh-ed25519 ') or len(public)>700:raise RuntimeError('HOLD_PUBLIC_KEY_FORMAT')
    if s.match(key,public):raise RuntimeError('HOLD_KEY_COLLISION')
    s.TRACK.write_text(json.dumps({'public':public,'key_id':None}));s.TRACK.chmod(0o600)
    s.api('POST',f'/instances/{INSTANCE}/ssh/',key,{'ssh_key':public})
    ids=[]
    for _ in range(6):
        ids=s.match(key,public)
        if ids:break
        time.sleep(2)
    if len(ids)!=1:raise RuntimeError('HOLD_KEY_ATTACH_NOT_VERIFIED')
    s.TRACK.write_text(json.dumps({'public':public,'key_id':ids[0]}))
    sock=s.RUNNER/'owner-ssh.sock'
    common=['ssh','-T','-i',str(s.KEY),'-p',str(port),'-o','BatchMode=yes','-o','IdentitiesOnly=yes',
         '-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','NumberOfPasswordPrompts=0',
         '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'-o','ControlPath='+str(sock)]
    host='root@'+ip
    # Authenticate the persistent connection, not a disposable 'true' session.
    # Retry only before any payload has been sent.
    for attempt in range(8):
        try:
            r=subprocess.run(common+['-o','ControlMaster=yes','-o','ControlPersist=90','-N','-f',host],capture_output=True,text=True,timeout=25)
        except subprocess.TimeoutExpired:r=None
        if r is not None and r.returncode==0 and sock.exists():
            MASTER=common+['-O','exit',host]
            break
        print('NOX_MAINT_AUTH_ATTEMPT='+str(attempt+1)+'_RETRY',flush=True)
        time.sleep(5)
    else:raise RuntimeError('HOLD_SSH_AUTHENTICATION')
    check=subprocess.run(common+['-O','check',host],capture_output=True,text=True,timeout=8)
    if check.returncode:raise RuntimeError('HOLD_SSH_MASTER_NOT_ALIVE')
    print('NOX_MAINT_AUTHENTICATED_INSTANCE=60509551',flush=True)
    payload=Path(FILES[action]).read_text()
    if action == 'subagent':
        assets=subagent_bundle_assets(SUBAGENT_BUNDLE_PATHS)
        payload=payload.replace('__NOX_BUNDLE_JSON__',json.dumps(assets))
    elif action == 'lifeline':
        assets={}
        for path in ('nox-control/nox_native_lifeline.py',
                     'nox-control/lifeline.example.json',
                     'nox-control/supervisor/nox-lifeline-guard.conf'):
            source=Path(path)
            if not source.is_file() or source.stat().st_size > 32768:
                raise RuntimeError('HOLD_LIFELINE_SOURCE_SCOPE')
            raw=source.read_bytes()
            assets[source.name]={'content':base64.b64encode(raw).decode('ascii'),
                                 'sha256':__import__('hashlib').sha256(raw).hexdigest()}
        payload=payload.replace('__NOX_BUNDLE_JSON__',json.dumps(assets))
    elif action in ('stage','repair'):
        assets={}
        for path in repair_bundle_paths(action,FILES[action],('nox-control/nox_cold_drive.py','nox-control/owner_native_audit.py',
                     'nox-control/owner_native_inspect.py','nox-control/hybrid_training_entry.py',
                     'nox-control/owner_capacity_probe.py','nox-control/owner_component_tasks.py',
                     'nox-control/owner_dispatcher_mentor.py','nox-control/nox_pc_export.py',
                     'nox-control/owner_chat_probe.py','nox-control/owner_native_repair.py',
                     'nox-control/owner_media_install.py','nox-control/owner_media_runtime.py',
                     'nox-control/owner_chat_source_patch.py','nox-control/owner_chat_stream.py',
                     'nox-control/owner_chat_ui.py','nox-control/owner-chat-ui.js','nox-control/owner-presence.js',
                     'nox-control/owner_event_outbox.py','nox-control/owner_chat_browser_qa.py',
                     'nox-control/owner_task_plans.py','nox-control/owner_task_lifecycle.py',
                     'nox-control/owner_task_lifecycle.json','nox-control/owner_senior_gateway.py',
                     'nox-control/owner_storage_reclaim.py','nox-control/owner_browser_diagnostic.py',
                     'nox-control/owner_storage_remaining_audit.py',
                     'nox-control/owner_s03_diagnostic.py','nox-control/owner_ram_duplicate_reclaim.py',
                     'nox-control/owner_browser_qa_entry.py',
                     'nox-control/owner_s03_prepare_entry.py','nox-control/owner_s03_gateway.py',
                     'nox-control/owner_s03_activate_entry.py','nox-control/owner_adapter_lineage_audit.py',
                     'nox-control/owner_s03_recover_activate.py','nox-control/owner_s03_content_reindex_entry.py',
                     'nox-control/owner_chat_layout_entry.py','nox-control/owner_chat_composer_entry.py',
                     'nox-control/owner_training_failure_probe.py',
                     'nox-control/owner_training_status.py','nox-control/owner_builder_proc_probe.py',
                     'nox-control/owner_builder_drive_public_proof.json',
                     'nox-control/owner_log_selected_size_probe.py','nox-control/owner_log_space_probe.py',
                     'nox-control/owner_browser_runtime_inspect.py',
                     'nox-control/owner_browser_stream_only_entry.py',
                     'nox-control/owner_browser_runtime_repair_entry.py','nox-control/owner_hermes_ram_preflight.py',
                     'nox-control/owner_training_status_entry.py','nox-control/owner_training_status_binding.py',
                     'nox-control/owner_training_amp_calibration.py','nox-control/owner_training_scaler_probe.py',
                     'nox-control/owner_training_placement_recovery.py','nox-control/owner_training_restore_preflight.py',
                     'nox-control/owner_calibration_receipt_read.py','nox-control/owner_chat_runtime_snapshot.py',
                     'nox-control/owner_browser_transport_qa_entry.py','nox-control/owner_chat_browser_transport_qa.py',
                     'nox-control/owner_browser_release_qa_entry.py','nox-control/owner_chat_browser_release_qa.py',
                     'nox-control/owner_chat_stream_only_qa.py',
                     'nox-control/owner_checkpoint_page_action.py',
                     'nox-control/owner_training_source_delta.py',
                     'nox-control/owner_chat_reports_state_entry.py',
                     'nox-control/owner_checkpoint_backup_transport.py','nox-control/owner_checkpoint_backup_export.py',
                     'nox-control/owner_checkpoint_backup_size_probe.py',
                     'nox-control/owner_checkpoint_backup_pager.py','nox-control/owner_checkpoint_backup_pager_entry.py',
                     'nox-control/owner_checkpoint_backup_deflated.py','nox-control/owner_checkpoint_backup_deflated_entry.py',
                     'nox-control/owner_training_restore_probe.py',
                     'nox-control/owner_checkpoint_backup_public_key.json',
                     'nox-control/owner_training_resume.py','nox-control/owner_training_recovery_entry.py',
                     'nox-control/owner_training_config_preflight.py','nox-control/owner_training_disk_guard.py',
                     'nox-control/owner_training_disk_guard_entry.py',
                     'nox-control/owner_training_recovery_chain.py','nox-control/owner_training_jsonl_recovery.py',
                     'nox-control/owner_training_jsonl_observe.py','nox-control/owner_training_recovery_observe.py',
                     'nox-control/owner_training_corpus_probe.py',
                     'nox-control/owner_chat_evidence_entry.py','nox-control/owner_chat_evidence.py',
                     'nox-control/owner_chat_evidence_patch.py',
                     'nox-control/owner_download_status_entry.py','nox-control/owner_download_status.py',
                     'nox-control/owner_capacity_measure_entry.py','nox-control/owner_media_fixture_export.py',
                     'nox-control/owner_media_fixture_transport.py','nox-control/owner_media_fixture_public_key.json',
                     'nox-control/owner_drive_ram_prepare.py','nox-control/owner_drive_ram_bridge.py',
                     'nox-control/owner_drive_ram_assets.json','nox-control/owner_drive_ram_envelope.json',
                     'nox_runpod/teacher_mesh/v112/native_v29_full_bridge.py',
                     'nox_runpod/teacher_mesh/v137/owner_self_observation.py',
                     'nox-control/owner_hermes_qa_batch.py',
                     'nox-control/owner_builder_cold_storage_entry.py',
                     'nox-control/owner_builder_archive_reclaim.py',
                     'nox-control/owner_qwen_disk_rearm_entry.py',
                     'nox-control/owner_builder_cold_location.py',
                     'nox-control/owner_drive_storage_bridge.py',
                     'nox-control/owner_builder_cold_chat_binding.py',
                     'nox-control/owner_hermes_warm_move.py',
                     'nox-control/owner_hermes_hydrate.py',
                     'coordination/onepass/nox-v135-resonance-owner-bridge.js',
                     'coordination/onepass/nox-v137-owner-self-status.js',
                     'nox-control/owner_qwen_training_status_entry.py',
                     'nox-control/owner_qwen_training_status.py',
                     'nox-control/owner_subagent_fresh_install_entry.py',
                     'nox-control/owner_subagent_dispatcher_fresh.py',
                     'nox-control/owner_subagent_hash_recovery_entry.py',
                     'nox-control/owner_subagent_install_entry.py',
                     'nox-control/pinned/qwen_status_v1/owner_qwen_training_observe.py',
                     'nox-control/owner_builder_extent_dedupe.py',
                     'nox-control/owner_qwen_media_handoff.py',
                     'nox-control/owner_media_training_handoff.py',
                     'nox-control/owner_qwen_window_entry.py',
                     'nox-control/owner_qwen_install_entry.py',
                     'nox-control/owner_qwen_guard_install_entry.py',
                     'nox-control/owner_qwen_guard_activate_entry.py',
                     'nox-control/owner_qwen_window_observe_entry.py',
                     'nox-control/owner_qwen_current_observe.py',
                     'nox-control/owner_qwen_execution_revision.py',
                     'nox-control/qwen_student_training_entry_revision.py',
                     'nox-control/owner_qwen_revision_guard.py',
                     'nox-control/owner_qwen_revision_status.py',
                     'nox-control/owner_qwen_revision_media_handoff.py',
                     'nox-control/owner_qwen_revision_media_guard.py',
                     'nox-control/owner_qwen_revision_handback_retry.py',
                     'nox-control/owner_hermes_revision_hydrate.py',
                     'nox-control/owner_qwen_revision_install.py',
                     'nox-control/owner_qwen_revision_rollback.py',
                     'nox-control/owner_qwen_revision_failed_diagnostic.json',
                     'nox-control/owner_qwen_retry_rollback.py',
                     'nox-control/owner_qwen_retry_failed_diagnostic.json',
                     'nox-control/owner_media_acceptance_entry.py',
                     'nox-control/owner_qwen_held_media_smoke.py',
                     'nox-control/owner_qwen_revision_observe.py',
                     'nox-control/owner_qwen_media_retry_observe.py',
                     'nox-control/owner_capacity_current_load_entry.py',
                     'nox-control/owner_qwen_training_guard.py',
                     'nox-control/owner_qwen_media_guard.py',
                     'nox-control/owner_qwen_media_handoff_entry.py',
                     'nox-control/owner_media_inbox_fair.py',
                     'nox-control/owner_media_inbox_fair_entry.py',
                     'nox-control/owner_qwen_handback_retry.py',
                     'nox-control/owner_subagent_instruction_truth.py',
                     'coordination/NOX_STORAGE_STREAMING_20261115/download_manifest.json')):
            p=Path(path)
            if p.is_file():assets[p.name]=base64.b64encode(p.read_bytes()).decode('ascii')
        payload=payload.replace('__NOX_BUNDLE_JSON__',json.dumps(assets))
    sha=os.environ['NOX_PINNED_SOURCE_SHA']
    script=f"set -euo pipefail\nNOX_OWNER_SOURCE_SHA={sha} NOX_OWNER_REQUEST_ID={int(request_id)} python3 - <<'NOX_OWNER_PAYLOAD'\n"+payload+"\nNOX_OWNER_PAYLOAD\n"
    timeout=150 if action in ('audit','inspect') else 900
    # Reuse the authenticated channel. A dead master must not fall back to
    # a fresh, potentially ambiguous TCP connection while starting a mutation.
    r=subprocess.run(common+['-o','ControlMaster=no','-o','ProxyCommand=false',host,'bash','-se'],input=script,capture_output=True,text=True,timeout=timeout)
    for line in r.stdout.splitlines():
        if line.startswith('NOX_MAINT_') and len(line)<180000:print(line,flush=True)
    print('NOX_MAINT_REMOTE_EXIT_CODE='+str(r.returncode),flush=True)
    if r.returncode:
        err=r.stderr.lower()
        cls='AUTH' if 'permission denied' in err else 'TIMEOUT' if 'timed out' in err else 'CONNECTION' if 'connect' in err else 'PAYLOAD'
        print('NOX_MAINT_FAILURE_CLASS='+cls,flush=True)
    marker='NOX_MAINT_'+action.upper()+'_COMPLETE=true'
    if r.returncode or marker not in r.stdout:raise RuntimeError('HOLD_NATIVE_PAYLOAD_INCOMPLETE')
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=FILES);args=p.parse_args();good=False
    try:
        request=authorize_event(args.action)
        print('NOX_MAINT_AUTHORIZED_COMMENT_ID='+str(request),flush=True)
        good=run_native(args.action,request)
    except Exception as e:
        code=str(e)
        print('NOX_MAINT_RESULT='+(code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else 'HOLD_'+type(e).__name__.upper()),flush=True)
    finally:
        if MASTER:
            with contextlib.suppress(Exception):subprocess.run(MASTER,capture_output=True,timeout=8)
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
        try:
            if not s.cleanup():good=False
        except Exception:print('NOX_MAINT_CLEANUP=HOLD');good=False
        with contextlib.suppress(OSError):s.KEY.unlink()
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
