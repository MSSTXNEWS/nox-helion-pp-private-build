#!/usr/bin/env python3
"""Explicit owner-command transport; one authenticated SSH session, pinned source.
No push/PR activation, no secret export, no blind retry of native mutations.
"""
from __future__ import annotations
import argparse, base64, contextlib, hashlib, ipaddress, json, os, re, shlex, socket, stat, subprocess, sys, time
from pathlib import Path
REPO='MSSTXNEWS/nox-helion-pp-private-build'
OWNER_ID=340718567
INSTANCE=60509551
PIN='SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'
FILES={'audit': 'nox-control/owner_native_audit.py', 'inspect': 'nox-control/owner_native_inspect.py', 'source_attest': 'nox-control/owner_chat_s03_source_attest.py', 'source_export': 'nox-control/owner_chat_s03_source_export.py', 'stage': 'nox-control/owner_native_stage.py', 'repair': 'nox-control/systemic_relay_20261118/owner_native_reflex_restore_entry.py', 'reflex_successor': 'nox-control/systemic_relay_20261118/owner_native_reflex_successor_entry.py', 'lifeline': 'nox-control/owner_native_lifeline.py'}
MASTER=None

# GitHub Actions may omit an individual log line above the operator's historical
# 180k character threshold. Preserve oversized evidence as small, independently
# verifiable records so consumers can detect missing, reordered, or corrupt data.
# Match the pre-existing Actions log gate exactly: Python character count.
MAX_FORWARD_LINE_CHARS=180000
MAX_FORWARD_LINE_BYTES=MAX_FORWARD_LINE_CHARS
TRANSFER_CHUNK_BYTES=16384
TRANSFER_MAX_BYTES=8*1024*1024
TRANSFER_PREFIX='NOX_MAINT_TRANSFER_'
AUDIT_PREFIX='NOX_MAINT_AUDIT='
AUDIT_COMPLETE='NOX_MAINT_AUDIT_COMPLETE=true'
AUDIT_SECTIONS=('hardware','process_rows','supervisor','packages','models','storage','mount_inventory')
INSPECT_SCOPE_MARKERS=frozenset(('CONFIG','INSTALLED_SOURCE','POST_QUEUE','POST_TASK','POST_WORKERS',
    'PROJECT_FILE','PROJECT_COVERAGE','ORIGINAL_QUEUE_PRESERVATION','OLD_REVIEW_PRESERVATION',
    'INSTALL_RECEIPT','SNAPSHOT_A','HOST_CLOCK_CHAIN','LOCKS','SNAPSHOT_B'))
STAGE_KINDS=frozenset(('source_installed','trainer_busy_no_change','installed_native_helpers',
    'nvml_dependency_install','native_gpu_library_smoke','teacher_controller_reload','llama_roles_before',
    'owned_gpu1_inference_yielded','gpu1_after_yield','manual_hold_released_by_explicit_owner_request',
    'existing_trainer_start','native_receipt','failure'))
TRANSFER_MARKER_RE=re.compile(r'^(NOX_MAINT_[A-Z0-9_]+)=')

def _transfer_record(kind,value):
    return TRANSFER_PREFIX+kind+'='+json.dumps(value,separators=(',',':'),sort_keys=True)

def _validate_forward_marker(action,line):
    """Allow only source markers with a fixed, known action-specific schema."""
    match=TRANSFER_MARKER_RE.match(line)
    if not match:raise RuntimeError('HOLD_REMOTE_MARKER_FORMAT')
    marker=match.group(1);payload=line[match.end():]
    if action=='inspect':
        if marker=='NOX_MAINT_INSPECT_COMPLETE':
            if payload!='true':raise RuntimeError('HOLD_REMOTE_MARKER_VALUE')
            return
        if marker=='NOX_MAINT_COMPONENTS':
            try:value=json.loads(payload)
            except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_REMOTE_MARKER_JSON') from exc
            if (not isinstance(value,dict) or set(value)!={'receipts','tasks','queue_scope'}
                    or not isinstance(value['receipts'],list) or not isinstance(value['tasks'],list)
                    or not isinstance(value['queue_scope'],str)):
                raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
            return
        prefix='NOX_MAINT_SCOPE_'
        scope=marker[len(prefix):] if marker.startswith(prefix) else None
        if scope not in INSPECT_SCOPE_MARKERS:raise RuntimeError('HOLD_REMOTE_MARKER_NOT_ALLOWLISTED')
        try:value=json.loads(payload)
        except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_REMOTE_MARKER_JSON') from exc
        if not isinstance(value,(dict,list)):raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
        return
    if action=='stage':
        if marker=='NOX_MAINT_STAGE_COMPLETE':
            if payload!='true':raise RuntimeError('HOLD_REMOTE_MARKER_VALUE')
            return
        if marker!='NOX_MAINT_STAGE':raise RuntimeError('HOLD_REMOTE_MARKER_NOT_ALLOWLISTED')
        try:value=json.loads(payload)
        except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_REMOTE_MARKER_JSON') from exc
        if (not isinstance(value,dict) or set(value)!={'kind','data'}
                or value.get('kind') not in STAGE_KINDS):
            raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
        return
    if action=='repair':
        if marker=='NOX_MAINT_REPAIR_COMPLETE':
            if payload!='true':raise RuntimeError('HOLD_REMOTE_MARKER_VALUE')
            return
        if marker!='NOX_MAINT_REFLEX_RESTORE':raise RuntimeError('HOLD_REMOTE_MARKER_NOT_ALLOWLISTED')
        try:value=json.loads(payload)
        except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_REMOTE_MARKER_JSON') from exc
        if not isinstance(value,dict):raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
        return
    if action=='reflex_successor':
        if marker=='NOX_MAINT_REFLEX_SUCCESSOR_COMPLETE':
            if payload!='true':raise RuntimeError('HOLD_REMOTE_MARKER_VALUE')
            return
        if marker not in ('NOX_MAINT_REFLEX_SUCCESSOR',
                          'NOX_MAINT_REFLEX_SUCCESSOR_HOLD'):
            raise RuntimeError('HOLD_REMOTE_MARKER_NOT_ALLOWLISTED')
        try:value=json.loads(payload)
        except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_REMOTE_MARKER_JSON') from exc
        if (not isinstance(value,dict)
                or value.get('schema')!='NOX_NATIVE_REFLEX_UPGRADE_RECEIPT_V1'
                or not re.fullmatch(r'[0-9a-f]{40}',str(value.get('source_sha','')))
                or not re.fullmatch(r'[0-9]{1,24}',str(value.get('request','')))):
            raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
        if marker.endswith('_HOLD'):
            if not re.fullmatch(r'HOLD_[A-Z0-9_]+',str(value.get('state',''))):
                raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
            return
        if (value.get('state')!='NATIVE_REFLEX_TELEMETRY_VERIFIED'
                or value.get('runtime_files_changed')!=3
                or type(value.get('new_native_jobs')) is not int
                or value.get('new_native_jobs')!=0
                or not re.fullmatch(r'[0-9a-f]{64}',str(value.get('base_manifest_sha256','')))
                or not re.fullmatch(r'[0-9a-f]{64}',str(value.get('monitor_observation_sha256','')))
                or not re.fullmatch(r'[0-9a-f]{64}',str(value.get('draft_manifest_sha256','')))
                or value.get('successor_proposal_sha256')!=value.get('draft_manifest_sha256')
                or value.get('successor_authority')!='PROPOSAL_ONLY'
                or not isinstance(value.get('successor_decisions'),list)
                or len(value['successor_decisions'])>64
                or not all(isinstance(row,dict) for row in value['successor_decisions'])
                or not isinstance(value.get('successor_draft_missions'),list)
                or len(value['successor_draft_missions'])>3
                or not all(isinstance(row,dict) for row in value['successor_draft_missions'])
                or not isinstance(value.get('successor_draft_manifest'),dict)
                or value['successor_draft_manifest'].get('review_origin')!='UNREVIEWED_REFLEX_DRAFT'
                or value['successor_draft_manifest'].get('acceptance_scope')!='DRAFT_ONLY'
                or value['successor_draft_manifest'].get('original_task_accepted') is not False
                or value.get('successor_required_next_step')!='INDEPENDENT_REVIEW_AND_OWNER_PINNED_MANIFEST_CAS'):
            raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
        draft_sha=hashlib.sha256(json.dumps(value['successor_draft_manifest'],
            ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        if draft_sha!=value['draft_manifest_sha256']:
            raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
        return
    if action=='lifeline':
        if marker=='NOX_MAINT_LIFELINE_COMPLETE':
            if payload!='true':raise RuntimeError('HOLD_REMOTE_MARKER_VALUE')
            return
        if marker!='NOX_MAINT_LIFELINE':raise RuntimeError('HOLD_REMOTE_MARKER_NOT_ALLOWLISTED')
        try:value=json.loads(payload)
        except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_REMOTE_MARKER_JSON') from exc
        if not isinstance(value,dict):raise RuntimeError('HOLD_REMOTE_MARKER_SCHEMA')
        return
    raise RuntimeError('HOLD_REMOTE_ACTION_NOT_ALLOWLISTED')

def build_transfer_records(marker_line,request_id,source_sha,force=False):
    """Encode one NOX marker into a bounded BEGIN/CHUNK*/END transfer."""
    match=TRANSFER_MARKER_RE.match(marker_line)
    if not match:raise RuntimeError('HOLD_TRANSFER_MARKER_FORMAT')
    if type(request_id) is not int or request_id<1:raise RuntimeError('HOLD_TRANSFER_REQUEST_ID')
    if not re.fullmatch(r'[0-9a-f]{40}',str(source_sha)):raise RuntimeError('HOLD_TRANSFER_SOURCE_SHA')
    raw=marker_line.encode('utf-8')
    if len(raw)>TRANSFER_MAX_BYTES:raise RuntimeError('HOLD_TRANSFER_ARTIFACT_OVERSIZE')
    if not force and len(marker_line)<MAX_FORWARD_LINE_CHARS:return [marker_line]
    digest=hashlib.sha256(raw).hexdigest()
    marker=match.group(1)
    artifact_id=hashlib.sha256((str(request_id)+'|'+source_sha+'|'+marker+'|'+digest+'|'+str(len(raw))).encode()).hexdigest()
    chunks=[raw[i:i+TRANSFER_CHUNK_BYTES] for i in range(0,len(raw),TRANSFER_CHUNK_BYTES)]
    common={'version':1,'request_id':request_id,'source_sha':source_sha,'artifact_id':artifact_id,
            'marker':marker,'total_bytes':len(raw),'chunk_count':len(chunks),'sha256':digest}
    records=[_transfer_record('BEGIN',common)]
    for index,chunk in enumerate(chunks):
        records.append(_transfer_record('CHUNK',{'artifact_id':artifact_id,'index':index,
            'chunk_count':len(chunks),'raw_bytes':len(chunk),'sha256':hashlib.sha256(chunk).hexdigest(),
            'data_b64':base64.b64encode(chunk).decode('ascii')}))
    records.append(_transfer_record('END',common))
    if any(len(line)>=MAX_FORWARD_LINE_CHARS for line in records):
        raise RuntimeError('HOLD_TRANSFER_RECORD_OVERSIZE')
    return records

def reassemble_transfer_records(records,expected_request_id,expected_source_sha):
    """Validate exact transfer shape, metadata, chunk hashes and whole SHA."""
    if type(expected_request_id) is not int or expected_request_id<1:
        raise RuntimeError('HOLD_TRANSFER_REQUEST_ID')
    if not re.fullmatch(r'[0-9a-f]{40}',str(expected_source_sha)):
        raise RuntimeError('HOLD_TRANSFER_SOURCE_SHA')
    if (not isinstance(records,(list,tuple)) or len(records)<3
            or len(records)>TRANSFER_MAX_BYTES//TRANSFER_CHUNK_BYTES+3):
        raise RuntimeError('HOLD_TRANSFER_RECORDS_MISSING')
    parsed=[]
    for line in records:
        if not isinstance(line,str) or len(line)>=MAX_FORWARD_LINE_CHARS:
            raise RuntimeError('HOLD_TRANSFER_RECORD_OVERSIZE')
        prefix,sep,payload=line.partition('=')
        if not sep or prefix not in (TRANSFER_PREFIX+'BEGIN',TRANSFER_PREFIX+'CHUNK',TRANSFER_PREFIX+'END'):
            raise RuntimeError('HOLD_TRANSFER_RECORD_FORMAT')
        try:value=json.loads(payload)
        except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_TRANSFER_RECORD_JSON') from exc
        if not isinstance(value,dict):raise RuntimeError('HOLD_TRANSFER_RECORD_JSON')
        parsed.append((prefix.rsplit('_',1)[1],value))
    kind,begin=parsed[0]
    end_kind,end=parsed[-1]
    keys={'version','request_id','source_sha','artifact_id','marker','total_bytes','chunk_count','sha256'}
    if kind!='BEGIN' or end_kind!='END' or set(begin)!=keys or set(end)!=keys or begin!=end:
        raise RuntimeError('HOLD_TRANSFER_BOUNDARY_MISMATCH')
    if (type(begin['version']) is not int or begin['version']!=1 or type(begin['request_id']) is not int
            or begin['request_id']!=expected_request_id or begin['source_sha']!=expected_source_sha
            or type(begin['total_bytes']) is not int or begin['total_bytes']<1
            or begin['total_bytes']>TRANSFER_MAX_BYTES or type(begin['chunk_count']) is not int
            or begin['chunk_count']<1
            or begin['chunk_count']!=(begin['total_bytes']+TRANSFER_CHUNK_BYTES-1)//TRANSFER_CHUNK_BYTES
            or not re.fullmatch(r'[0-9a-f]{64}',str(begin['sha256']))
            or not re.fullmatch(r'NOX_MAINT_[A-Z0-9_]+',str(begin['marker']))
            or not re.fullmatch(r'[0-9a-f]{64}',str(begin['artifact_id']))):
        raise RuntimeError('HOLD_TRANSFER_METADATA_INVALID')
    chunk_rows=parsed[1:-1]
    if len(chunk_rows)!=begin['chunk_count']:raise RuntimeError('HOLD_TRANSFER_CHUNK_COUNT')
    parts=[]
    for expected_index,(chunk_kind,row) in enumerate(chunk_rows):
        if chunk_kind!='CHUNK' or set(row)!={'artifact_id','index','chunk_count','raw_bytes','sha256','data_b64'}:
            raise RuntimeError('HOLD_TRANSFER_CHUNK_FORMAT')
        if (row['artifact_id']!=begin['artifact_id'] or type(row['index']) is not int
                or row['index']!=expected_index or type(row['chunk_count']) is not int
                or row['chunk_count']!=begin['chunk_count'] or type(row['raw_bytes']) is not int
                or row['raw_bytes']<1 or row['raw_bytes']>TRANSFER_CHUNK_BYTES
                or not re.fullmatch(r'[0-9a-f]{64}',str(row['sha256']))
                or not isinstance(row['data_b64'],str)):
            raise RuntimeError('HOLD_TRANSFER_CHUNK_METADATA')
        try:part=base64.b64decode(row['data_b64'],validate=True)
        except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_TRANSFER_CHUNK_BASE64') from exc
        if len(part)!=row['raw_bytes'] or hashlib.sha256(part).hexdigest()!=row['sha256']:
            raise RuntimeError('HOLD_TRANSFER_CHUNK_SHA')
        if expected_index<len(chunk_rows)-1 and len(part)!=TRANSFER_CHUNK_BYTES:
            raise RuntimeError('HOLD_TRANSFER_CHUNK_SIZE')
        parts.append(part)
    raw=b''.join(parts)
    if len(raw)!=begin['total_bytes'] or hashlib.sha256(raw).hexdigest()!=begin['sha256']:
        raise RuntimeError('HOLD_TRANSFER_TOTAL_SHA')
    try:decoded=raw.decode('utf-8',errors='strict')
    except UnicodeDecodeError as exc:raise RuntimeError('HOLD_TRANSFER_UTF8') from exc
    marker_match=TRANSFER_MARKER_RE.match(decoded)
    if not marker_match or marker_match.group(1)!=begin['marker']:
        raise RuntimeError('HOLD_TRANSFER_MARKER_MISMATCH')
    expected_id=hashlib.sha256((str(expected_request_id)+'|'+expected_source_sha+'|'+begin['marker']+'|'+begin['sha256']+'|'+str(len(raw))).encode()).hexdigest()
    if expected_id!=begin['artifact_id']:raise RuntimeError('HOLD_TRANSFER_ARTIFACT_ID')
    return raw

def _safe_audit_comm(value):
    return (isinstance(value,str) and 1<=len(value)<=60
            and re.fullmatch(r'[A-Za-z0-9_.+@= -]{1,60}',value) is not None)

def _project_identity(identity):
    if not isinstance(identity,dict):return None
    fields=('pid','ppid','start_ticks','nspid','nspid_available',
            'pid_namespace','mnt_namespace','cgroup_namespace','identity_state')
    result={key:identity[key] for key in fields if key in identity}
    if 'comm' in identity:
        result['comm']=identity['comm'] if _safe_audit_comm(identity['comm']) else 'UNSAFE_OR_UNAVAILABLE'
    return result

def _project_gpu_snapshot(snapshot):
    if not isinstance(snapshot,dict):raise RuntimeError('HOLD_AUDIT_GPU_SNAPSHOT_SHAPE')
    fields=('return_code','started_unix_ns','finished_unix_ns','rejected_rows',
            'unbounded','truncated','complete','scope')
    result={key:snapshot[key] for key in fields if key in snapshot}
    apps=snapshot.get('apps')
    if not isinstance(apps,list):raise RuntimeError('HOLD_AUDIT_GPU_APPS_SHAPE')
    result['apps']=[]
    for row in apps:
        if not isinstance(row,dict) or set(row)!={'gpu_pid','gpu_uuid','used_gpu_memory'}:
            raise RuntimeError('HOLD_AUDIT_GPU_APP_ROW')
        if (type(row.get('gpu_pid')) is not int or row['gpu_pid']<=1
                or not re.fullmatch(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',str(row.get('gpu_uuid')))
                or not isinstance(row.get('used_gpu_memory'),str)
                or not (row['used_gpu_memory'].isdecimal()
                        or row['used_gpu_memory'].lower() in ('n/a','not supported'))):
            raise RuntimeError('HOLD_AUDIT_GPU_APP_ROW')
        result['apps'].append({key:row[key] for key in ('gpu_pid','gpu_uuid','used_gpu_memory')})
    return result

def _project_service_inventory(services):
    if not isinstance(services,dict):raise RuntimeError('HOLD_AUDIT_SUPERVISOR_INVENTORY_SHAPE')
    fields=('command_rc','command_success','inventory_complete','rows_complete',
            'status_consistent','truncated','rejected_lines','duplicate_service_names',
            'identity_complete','scope')
    result={key:services[key] for key in fields if key in services}
    health=services.get('service_health')
    if not isinstance(health,dict):raise RuntimeError('HOLD_AUDIT_SUPERVISOR_HEALTH_SHAPE')
    result['service_health']={key:health[key] for key in ('state','counts','running','not_running') if key in health}
    raw_rows=services.get('services')
    if not isinstance(raw_rows,list):raise RuntimeError('HOLD_AUDIT_SUPERVISOR_SERVICE_ROWS')
    result['services']=[]
    for row in raw_rows:
        allowed={'service','state','pid','identity','identity_state'}
        if (not isinstance(row,dict) or not {'service','state','pid','identity'}.issubset(row)
                or set(row)-allowed or not isinstance(row.get('service'),str)
                or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',row['service'])
                or row.get('state') not in ('RUNNING','STARTING','STOPPED','FATAL','BACKOFF','EXITED','STOPPING','UNKNOWN')
                or (row.get('pid') is not None and (type(row['pid']) is not int or row['pid']<=1))
                or (row.get('identity') is not None and not isinstance(row['identity'],dict))
                or (row.get('identity_state') is not None and not isinstance(row['identity_state'],str))):
            raise RuntimeError('HOLD_AUDIT_SUPERVISOR_SERVICE_ROW')
        item={key:row[key] for key in ('service','state','pid','identity_state') if key in row}
        if isinstance(row.get('identity'),dict):item['identity']=_project_identity(row['identity'])
        else:item['identity']=None
        result['services'].append(item)
    duplicate_names=services.get('duplicate_service_names')
    if type(duplicate_names) is not bool:
        raise RuntimeError('HOLD_AUDIT_SUPERVISOR_DUPLICATE_FLAG')
    names=[row['service'] for row in result['services']]
    if duplicate_names is False and len(names)!=len(set(names)):
        raise RuntimeError('HOLD_AUDIT_SUPERVISOR_DUPLICATE_DECLARATION')
    return result

def _project_gpu_link(link):
    if not isinstance(link,dict):raise RuntimeError('HOLD_AUDIT_GPU_LINK_ROW')
    fields=('gpu_pid','gpu_uuid','used_gpu_memory_before','used_gpu_memory_after',
            'inventory_presence','identity_stability','classification','evidence_state',
            'visibility','before_alias_scan_complete','after_alias_scan_complete','scope')
    result={key:link[key] for key in fields if key in link}
    identity=link.get('proc_identity')
    if identity is not None and not isinstance(identity,dict):
        raise RuntimeError('HOLD_AUDIT_GPU_IDENTITY_ROW')
    if isinstance(identity,dict):result['proc_identity']=_project_identity(identity)
    match=link.get('service_match')
    if match is not None:
        if (not isinstance(match,dict)
                or set(match)!={'service','pid','state','relation','start_ticks'}
                or not isinstance(match.get('service'),str)
                or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',match['service'])
                or type(match.get('pid')) is not int or match['pid']<=1
                or match.get('state') not in ('RUNNING','STARTING')
                or match.get('relation') not in ('DIRECT_PID','PARENT_CHAIN')
                or type(match.get('start_ticks')) is not int or match['start_ticks']<=0):
            raise RuntimeError('HOLD_AUDIT_GPU_SERVICE_MATCH')
        result['service_match']={key:match[key] for key in ('service','pid','state','relation','start_ticks')}
    else:result['service_match']=None
    chain=link.get('parent_chain')
    if not isinstance(chain,list):raise RuntimeError('HOLD_AUDIT_GPU_PARENT_CHAIN_SHAPE')
    projected_chain=[]
    for row in chain:
        if (not isinstance(row,dict)
                or not {'pid','ppid','start_ticks','pid_namespace'}.issubset(row)
                or set(row)-{'pid','ppid','start_ticks','pid_namespace','comm','cgroups'}
                or type(row.get('pid')) is not int or row['pid']<=1
                or type(row.get('ppid')) is not int or row['ppid']<0
                or type(row.get('start_ticks')) is not int or row['start_ticks']<=0
                or (row.get('pid_namespace') is not None
                    and (not isinstance(row.get('pid_namespace'),str)
                         or not re.fullmatch(r'pid:\[[0-9]+\]',row['pid_namespace'])))):
            raise RuntimeError('HOLD_AUDIT_GPU_PARENT_CHAIN_ROW')
        projected_chain.append({key:row[key] for key in ('pid','ppid','start_ticks','pid_namespace')})
    result['parent_chain']=projected_chain
    return result

def _project_hardware(result):
    if not isinstance(result,dict):return None
    return {'gpu_apps_before':_project_gpu_snapshot(result.get('gpu_apps_before')),
            'gpu_apps_after':_project_gpu_snapshot(result.get('gpu_apps_after')),
            'gpu_process_links':([_project_gpu_link(row) for row in result['gpu_process_links']]
                                 if isinstance(result.get('gpu_process_links'),list) else None),
            'supervisor_services':_project_service_inventory(result.get('supervisor_services'))}

def _project_supervisor_worker(result):
    if not isinstance(result,dict):raise RuntimeError('HOLD_AUDIT_SUPERVISOR_WORKER_SHAPE')
    output={'available':result.get('available') is True,'attempt_count':None,'results':[]}
    attempts=result.get('results')
    if attempts is None and output['available'] is False:
        attempts=[]
    if not isinstance(attempts,list):raise RuntimeError('HOLD_AUDIT_SUPERVISOR_ATTEMPTS_SHAPE')
    for attempt in attempts:
        if not isinstance(attempt,dict):raise RuntimeError('HOLD_AUDIT_SUPERVISOR_ATTEMPT_ROW')
        rows=attempt.get('services')
        if not isinstance(rows,list):raise RuntimeError('HOLD_AUDIT_SUPERVISOR_ATTEMPT_SERVICES')
        safe_rows=[]
        for row in rows:
            if (not isinstance(row,dict) or set(row)!={'name','state','pid'}
                    or not isinstance(row.get('name'),str)
                    or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',row['name'])
                    or row.get('state') not in ('RUNNING','STARTING','STOPPED','FATAL','BACKOFF','EXITED','STOPPING','UNKNOWN')
                    or (row.get('pid') is not None and (type(row['pid']) is not int or row['pid']<=1))):
                raise RuntimeError('HOLD_AUDIT_SUPERVISOR_ATTEMPT_SERVICE_ROW')
            safe_rows.append({key:row[key] for key in ('name','state','pid')})
        rc=attempt.get('rc')
        if type(rc) is not int:raise RuntimeError('HOLD_AUDIT_SUPERVISOR_ATTEMPT_RC')
        output['results'].append({'rc':rc,'services':safe_rows})
    output['attempt_count']=len(attempts)
    if output['attempt_count']!=len(output['results']):
        raise RuntimeError('HOLD_AUDIT_SUPERVISOR_ATTEMPT_COUNT')
    return output

def _supervisor_attempt_count_matches(snapshot):
    if not isinstance(snapshot,dict):return False
    attempts=snapshot.get('results')
    return (type(snapshot.get('attempt_count')) is int and isinstance(attempts,list)
            and snapshot['attempt_count']==len(attempts))

def _validate_audit_process_inventory(inventory):
    if not isinstance(inventory,dict):return None
    inventory_keys={'scope','started_unix_ns','finished_unix_ns','entries_seen','row_count','cap',
        'truncated','enumeration_error','read_failure_count','read_failure_pids','complete',
        'fields','omitted_fields','rows_sha256','rows'}
    if set(inventory)!=inventory_keys:
        raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_KEYS')
    process_rows=inventory.get('rows')
    expected_fields=['pid','ppid','uid','start_ticks','nspid','namespaces.pid',
        'namespaces.mnt','namespaces.cgroup','comm','exe','exe_state']
    expected_omitted=['argv','cmdline','environ','cgroup_paths']
    if (not isinstance(process_rows,list) or type(inventory.get('complete')) is not bool
            or type(inventory.get('truncated')) is not bool
            or inventory.get('scope')!='ALL_NUMERIC_PROC_PIDS_MINIMAL_IDENTITY'
            or type(inventory.get('row_count')) is not int or inventory['row_count']<1
            or inventory['row_count']!=len(process_rows)
            or type(inventory.get('cap')) is not int or inventory['cap']!=8192
            or type(inventory.get('entries_seen')) is not int
            or not inventory['row_count']<=inventory['entries_seen']<=inventory['cap']+1
            or type(inventory.get('read_failure_count')) is not int
            or not 0<=inventory['read_failure_count']<=inventory['row_count']
            or not isinstance(inventory.get('read_failure_pids'),list)
            or len(inventory['read_failure_pids'])>64
            or any(type(pid) is not int or pid<1 for pid in inventory['read_failure_pids'])
            or type(inventory.get('started_unix_ns')) is not int
            or type(inventory.get('finished_unix_ns')) is not int
            or inventory['started_unix_ns']<=0 or inventory['finished_unix_ns']<inventory['started_unix_ns']
            or inventory.get('fields')!=expected_fields or inventory.get('omitted_fields')!=expected_omitted
            or 'enumeration_error' not in inventory
            or (inventory['enumeration_error'] is not None
                and not re.fullmatch(r'[A-Za-z0-9_]{1,64}',str(inventory['enumeration_error'])))
            or not re.fullmatch(r'[0-9a-f]{64}',str(inventory.get('rows_sha256')))):
        raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_SHAPE')
    row_keys={'pid','ppid','uid','start_ticks','nspid','namespaces','comm','exe','exe_state','identity_state'}
    missing_field_names={'pid','ppid','uid','start_ticks','nspid','namespace_pid','namespace_mnt',
        'namespace_cgroup','comm','exe_read','exe'}
    pids=[]
    for row in process_rows:
        if not isinstance(row,dict) or not row_keys.issubset(row) or set(row)-row_keys-{'missing_fields'}:
            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_ROW_KEYS')
        if type(row.get('pid')) is not int or row['pid']<1:
            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_ROW_PID')
        if 'missing_fields' in row and (not isinstance(row['missing_fields'],list)
                or len(row['missing_fields'])>len(missing_field_names)
                or any(not isinstance(name,str) or name not in missing_field_names for name in row['missing_fields'])
                or row['missing_fields']!=sorted(set(row['missing_fields']))):
            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_MISSING_FIELDS')
        if row.get('identity_state') not in ('VERIFIED','IDENTITY_INCOMPLETE','UNAVAILABLE_OR_CHANGED'):
            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_IDENTITY_STATE')
        if ((row['identity_state']=='IDENTITY_INCOMPLETE'
                and ('missing_fields' not in row or not row['missing_fields']))
                or (row['identity_state']!='IDENTITY_INCOMPLETE' and 'missing_fields' in row)):
            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_MISSING_FIELDS')
        if ((row.get('ppid') is not None and (type(row['ppid']) is not int or row['ppid']<0))
                or (row.get('uid') is not None and (type(row['uid']) is not int or row['uid']<0))
                or (row.get('start_ticks') is not None and (type(row['start_ticks']) is not int or row['start_ticks']<=0))
                or (row.get('nspid') is not None and (not isinstance(row['nspid'],list) or not row['nspid']
                    or len(row['nspid'])>16 or any(type(value) is not int or value<1 for value in row['nspid'])))
                or not isinstance(row.get('namespaces'),dict) or set(row['namespaces'])!={'pid','mnt','cgroup'}
                or any(value is not None and (not isinstance(value,str)
                    or not re.fullmatch(rf'{name}:\[[0-9]+\]',value))
                    for name,value in row['namespaces'].items())
                or (row.get('comm') is not None and not _safe_audit_comm(row['comm']))
                or row.get('exe_state') not in ('AVAILABLE','MISSING','UNAVAILABLE','UNREADABLE','REDACTED')
                or (row.get('exe') is not None and row['exe']!='[REDACTED]'
                    and (not isinstance(row['exe'],str)
                         or not re.fullmatch(r'[A-Za-z0-9_.+@= -]{1,256}',row['exe'])))):
            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_ROW_VALUE')
        if row['identity_state']=='VERIFIED':
            if (type(row.get('ppid')) is not int or row.get('uid') is None
                    or row.get('start_ticks') is None or not isinstance(row.get('nspid'),list)
                    or any(value is None for value in row['namespaces'].values())
                    or not _safe_audit_comm(row.get('comm'))
                    or row.get('exe_state') not in ('AVAILABLE','MISSING')
                    or (row.get('exe_state')=='AVAILABLE' and row.get('exe') in (None,'[REDACTED]'))
                    or (row.get('exe_state')=='MISSING' and row.get('exe') is not None)):
                raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_VERIFIED_ROW')
        if row['identity_state']=='IDENTITY_INCOMPLETE' and 'missing_fields' not in row:
            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_MISSING_FIELDS')
        pids.append(row['pid'])
    if pids!=sorted(set(pids)):
        raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_PID_ORDER')
    digest=hashlib.sha256(json.dumps(process_rows,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    if digest!=inventory['rows_sha256']:
        raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_SHA')
    if inventory['complete']:
        if (inventory['truncated'] or inventory['enumeration_error'] is not None
                or inventory['read_failure_count']!=0 or inventory['read_failure_pids']
                or inventory['entries_seen']!=inventory['row_count']
                or any(row['identity_state']!='VERIFIED' for row in process_rows)):
            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_CONTRADICTION')
        for row in process_rows:
            nspid=row.get('nspid');namespaces=row.get('namespaces')
            if (type(row.get('ppid')) is not int or row['ppid']<0
                    or type(row.get('uid')) is not int or row['uid']<0
                    or type(row.get('start_ticks')) is not int or row['start_ticks']<=0
                    or not isinstance(nspid,list) or not nspid or len(nspid)>16
                    or any(type(pid) is not int or pid<1 for pid in nspid)
                    or not isinstance(namespaces,dict) or set(namespaces)!={'pid','mnt','cgroup'}
                    or any(not isinstance(namespaces.get(ns),str)
                           or not re.fullmatch(rf'{ns}:\[[0-9]+\]',namespaces[ns])
                           for ns in ('pid','mnt','cgroup'))
                    or not _safe_audit_comm(row.get('comm'))
                    or row.get('exe_state') not in ('AVAILABLE','MISSING')
                    or (row['exe_state']=='AVAILABLE' and (not isinstance(row.get('exe'),str)
                        or not re.fullmatch(r'[A-Za-z0-9_.+@= -]{1,256}',row['exe'])))
                    or (row['exe_state']=='MISSING' and row.get('exe') is not None)):
                raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_IDENTITY')
    return inventory

def audit_bundle_line(stdout):
    """Build a minimal, sanitized bundle; validate all seven worker records."""
    rows={};positions=[];complete_positions=[]
    for position,line in enumerate(stdout.splitlines()):
        if line==AUDIT_COMPLETE:complete_positions.append(position)
        if not line.startswith(AUDIT_PREFIX):continue
        try:row=json.loads(line[len(AUDIT_PREFIX):])
        except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_AUDIT_ROW_INVALID') from exc
        if not isinstance(row,dict) or row.get('section') not in AUDIT_SECTIONS:
            raise RuntimeError('HOLD_AUDIT_SECTION_INVALID')
        section=row['section']
        if section in rows:raise RuntimeError('HOLD_AUDIT_SECTION_DUPLICATE')
        if type(row.get('worker_pid')) is not int or row['worker_pid']<1:
            raise RuntimeError('HOLD_AUDIT_WORKER_IDENTITY')
        rows[section]=row;positions.append(position)
    if (len(complete_positions)!=1 or list(rows)!=list(AUDIT_SECTIONS)
            or complete_positions[0]<max(positions)):
        raise RuntimeError('HOLD_AUDIT_RECORD_SET_INCOMPLETE')

    for section in AUDIT_SECTIONS:
        row=rows[section]
        if 'error' in row:
            raise RuntimeError('HOLD_AUDIT_WORKER_INCOMPLETE')
        expected_result_type=list if section=='process_rows' else dict
        if ('result' not in row
                or not isinstance(row['result'],expected_result_type)):
            raise RuntimeError('HOLD_AUDIT_WORKER_RESULT_SHAPE')

    status_rows=[]
    for section in AUDIT_SECTIONS:
        row=rows[section]
        status_rows.append({'section':section,'worker_pid':row['worker_pid'],
            'status':'ERROR' if 'error' in row else 'PRESENT' if 'result' in row else 'MISSING_RESULT'})
    if any(row['status']!='PRESENT' for row in status_rows):
        raise RuntimeError('HOLD_AUDIT_WORKER_INCOMPLETE')
    hardware_row=rows['hardware']
    process_row=rows['process_rows']
    supervisor_row=rows['supervisor']
    hardware=_project_hardware(hardware_row.get('result')) if 'error' not in hardware_row else None
    supervisor=_project_supervisor_worker(supervisor_row.get('result')) if 'error' not in supervisor_row else None
    inventory=None
    if 'error' not in process_row:
        inventory=_validate_audit_process_inventory(process_row.get('bounded_process_identity_inventory'))
    filtered_rows=process_row.get('result')
    if not isinstance(filtered_rows,list) or len(filtered_rows)>356:
        raise RuntimeError('HOLD_AUDIT_FILTERED_PROCESS_ROWS')
    gpu_consumer_pids=[]
    allowed_process_keys={'pid','comm','executable','arguments','gpu_consumer','start_ticks','gpu_identity','scripts'}
    links=hardware.get('gpu_process_links') if isinstance(hardware,dict) else None
    links_by_gpu_pid={link.get('gpu_pid'):link for link in links if isinstance(link,dict)} if isinstance(links,list) else {}
    for item in filtered_rows:
        if (not isinstance(item,dict) or not {'pid','comm','executable','arguments','gpu_consumer','start_ticks'}.issubset(item)
                or set(item)-allowed_process_keys or type(item.get('pid')) is not int or item['pid']<1
                or type(item.get('start_ticks')) is not int or item['start_ticks']<=0
                or type(item.get('gpu_consumer')) is not bool or not isinstance(item.get('arguments'),list)
                or ('scripts' in item and not isinstance(item['scripts'],list))):
            raise RuntimeError('HOLD_AUDIT_FILTERED_PROCESS_ROW')
        if item['gpu_consumer']:
            gpu_identity=item.get('gpu_identity')
            gpu_identity_keys={'gpu_pid','start_ticks','nspid','pid_namespace','mnt_namespace',
                'cgroup_namespace','classification','visibility'}
            link=links_by_gpu_pid.get(gpu_identity.get('gpu_pid')) if isinstance(gpu_identity,dict) else None
            identity=link.get('proc_identity') if isinstance(link,dict) else None
            if (not isinstance(gpu_identity,dict) or set(gpu_identity)!=gpu_identity_keys
                    or not isinstance(identity,dict) or item['pid']!=identity.get('pid')
                    or item['start_ticks']!=identity.get('start_ticks')
                    or gpu_identity.get('start_ticks')!=identity.get('start_ticks')
                    or gpu_identity.get('nspid')!=identity.get('nspid')
                    or any(gpu_identity.get(field)!=identity.get(source) for field,source in (
                        ('pid_namespace','pid_namespace'),('mnt_namespace','mnt_namespace'),
                        ('cgroup_namespace','cgroup_namespace')))
                    or gpu_identity.get('classification')!=link.get('classification')
                    or gpu_identity.get('visibility')!=link.get('visibility')):
                raise RuntimeError('HOLD_AUDIT_FILTERED_GPU_IDENTITY')
            gpu_consumer_pids.append(item['pid'])
    process_summary={'filtered_row_count':len(filtered_rows) if filtered_rows is not None else None,
        'gpu_consumer_pids':sorted(set(gpu_consumer_pids)),
        'arguments_omitted':True,'scripts_omitted':True}
    bundle={'schema':'NOX_NATIVE_AUDIT_OUTPUT_BUNDLE_V1',
        'worker_sections':status_rows,
        'redacted_fields':['process_rows.result.arguments','process_rows.result.scripts',
            'hardware.supervisor_services.services.identity.cgroups',
            'hardware.gpu_process_links.proc_identity.cgroups',
            'hardware.gpu_process_links.parent_chain.cgroups',
            'packages','models','storage','mount_inventory'],
        'hardware':hardware,
        'process_rows':{'filtered_summary':process_summary,
            'bounded_process_identity_inventory':inventory},
        'supervisor':supervisor}
    return 'NOX_MAINT_AUDIT_BUNDLE='+json.dumps(bundle,separators=(',',':'),sort_keys=True)

def audit_census_status(stdout):
    """Return independent process, Supervisor, and GPU acceptance gates."""
    bundle_line=audit_bundle_line(stdout)
    bundle=json.loads(bundle_line.split('=',1)[1])
    process_section=bundle.get('process_rows') if isinstance(bundle,dict) else None
    process=process_section.get('bounded_process_identity_inventory') if isinstance(process_section,dict) else None
    process_rows=process.get('rows') if isinstance(process,dict) else None
    process_complete=(isinstance(process,dict) and process.get('complete') is True
        and not process.get('truncated') and process.get('enumeration_error') is None
        and process.get('read_failure_count')==0
        and process.get('entries_seen')==process.get('row_count')==len(process_rows)
        and process.get('row_count')>=1 and process.get('row_count')<=process.get('cap')
        and isinstance(process_rows,list))
    process_by_pid={row['pid']:row for row in process_rows if isinstance(row,dict) and type(row.get('pid')) is int} if isinstance(process_rows,list) else {}

    hardware=bundle.get('hardware') if isinstance(bundle,dict) else None
    services=hardware.get('supervisor_services') if isinstance(hardware,dict) else None
    service_rc=services.get('command_rc') if isinstance(services,dict) else None
    service_health_row=services.get('service_health') if isinstance(services,dict) else None
    service_health=service_health_row.get('state') if isinstance(service_health_row,dict) else None
    expected_health={0:'HEALTHY',3:'DEGRADED'}.get(service_rc)
    supervisor_complete=(isinstance(services,dict) and services.get('inventory_complete') is True
        and services.get('rows_complete') is True and services.get('status_consistent') is True
        and type(service_rc) is int and service_rc in (0,3)
        and services.get('command_success') is (service_rc==0)
        and services.get('truncated') is False and services.get('rejected_lines')==0
        and services.get('duplicate_service_names') is False and services.get('identity_complete') is True
        and service_health==expected_health and isinstance(services.get('services'),list)
        and bool(services['services']))
    if supervisor_complete:
        counts={}
        for service in services['services']:
            if not isinstance(service,dict) or not isinstance(service.get('service'),str):
                supervisor_complete=False;break
            state=service.get('state')
            if state not in ('RUNNING','STARTING','STOPPED','FATAL','BACKOFF','EXITED','STOPPING','UNKNOWN'):
                supervisor_complete=False;break
            counts[state]=counts.get(state,0)+1
        if supervisor_complete:
            health_counts=service_health_row.get('counts') if isinstance(service_health_row,dict) else None
            all_running=counts.get('RUNNING',0)==len(services['services'])
            supervisor_complete=(health_counts==counts
                and service_health_row.get('running')==counts.get('RUNNING',0)
                and service_health_row.get('not_running')==sum(count for state,count in counts.items() if state!='RUNNING')
                and ((service_rc==0 and all_running) or (service_rc==3 and not all_running)))
    supervisor_worker=bundle.get('supervisor') if isinstance(bundle,dict) else None
    supervisor_results=supervisor_worker.get('results') if isinstance(supervisor_worker,dict) else None
    crosscheck_complete=False
    if (supervisor_complete and isinstance(supervisor_worker,dict)
            and supervisor_worker.get('available') is True and isinstance(supervisor_results,list)
            and _supervisor_attempt_count_matches(supervisor_worker)):
        nonempty=[result for result in supervisor_results if isinstance(result,dict)
                  and isinstance(result.get('services'),list) and result['services']]
        if len(nonempty)==1:
            independent=nonempty[0]
            raw_rows=independent.get('services')
            hardware_rows=services.get('services')
            if (independent.get('rc')==service_rc and type(independent.get('rc')) is int
                    and isinstance(raw_rows,list) and isinstance(hardware_rows,list)):
                def normalized_service_rows(rows,name_key):
                    normalized=[]
                    for row in rows:
                        if not isinstance(row,dict):return None
                        name=row.get(name_key);state=row.get('state');pid=row.get('pid')
                        if (not isinstance(name,str) or not name
                                or state not in ('RUNNING','STARTING','STOPPED','FATAL','BACKOFF','EXITED','STOPPING','UNKNOWN')
                                or (pid is not None and (type(pid) is not int or pid<1))):return None
                        normalized.append((name,state,pid))
                    if len({item[0] for item in normalized})!=len(normalized):return None
                    return sorted(normalized)
                normalized_raw=normalized_service_rows(raw_rows,'name')
                normalized_hardware=normalized_service_rows(hardware_rows,'service')
                crosscheck_complete=(normalized_raw is not None and normalized_hardware is not None
                    and normalized_raw==normalized_hardware)

    before=hardware.get('gpu_apps_before') if isinstance(hardware,dict) else None
    after=hardware.get('gpu_apps_after') if isinstance(hardware,dict) else None
    links=hardware.get('gpu_process_links') if isinstance(hardware,dict) else None
    def gpu_inventory_valid(snapshot):
        if not isinstance(snapshot,dict) or snapshot.get('complete') is not True or snapshot.get('truncated') is not False:
            return False
        if (type(snapshot.get('return_code')) is not int or snapshot.get('return_code')!=0
                or type(snapshot.get('rejected_rows')) is not int or snapshot.get('rejected_rows')!=0
                or snapshot.get('unbounded') is not False):return False
        apps=snapshot.get('apps')
        if not isinstance(apps,list):return False
        valid=all(type(app.get('gpu_pid')) is int and app['gpu_pid']>1
            and re.fullmatch(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',str(app.get('gpu_uuid')))
            and isinstance(app.get('used_gpu_memory'),str)
            and (app['used_gpu_memory'].isdecimal() or app['used_gpu_memory'].lower() in ('n/a','not supported'))
            for app in apps if isinstance(app,dict)) and all(isinstance(app,dict) for app in apps)
        keys=[(app['gpu_pid'],app['gpu_uuid']) for app in apps] if valid else []
        return valid and len(keys)==len(set(keys))
    expected_links=set()
    if gpu_inventory_valid(before) and gpu_inventory_valid(after):
        expected_links={(app['gpu_pid'],app['gpu_uuid']) for app in before['apps']+after['apps']}
    observed_links=set();links_valid=isinstance(links,list)
    supervisor_services=services.get('services',[]) if isinstance(services,dict) else []
    def service_link_valid(link,classification):
        service_match=link.get('service_match')
        if classification=='NO_SERVICE_ANCESTOR':return service_match is None
        if classification=='MATCHED' and not isinstance(service_match,dict):return False
        if service_match is None:return classification=='NAMESPACE_ALIAS'
        if not isinstance(service_match,dict):return False
        if (service_match.get('relation') not in ('DIRECT_PID','PARENT_CHAIN')
                or service_match.get('state')!='RUNNING' or type(service_match.get('pid')) is not int
                or service_match['pid']<=1 or type(service_match.get('start_ticks')) is not int
                or service_match['start_ticks']<=0):return False
        matches=[service for service in supervisor_services if isinstance(service,dict)
            and service.get('service')==service_match.get('service') and service.get('state')=='RUNNING'
            and service.get('pid')==service_match['pid'] and isinstance(service.get('identity'),dict)
            and service['identity'].get('pid')==service_match['pid']
            and service['identity'].get('start_ticks')==service_match['start_ticks']]
        if len(matches)!=1:return False
        if service_match['relation']=='DIRECT_PID':
            return service_match['pid']==link.get('proc_identity',{}).get('pid') and service_match['start_ticks']==link.get('proc_identity',{}).get('start_ticks')
        chain=link.get('parent_chain')
        supervisor_identity=matches[0].get('identity')
        return (isinstance(chain,list) and isinstance(supervisor_identity,dict)
            and any(isinstance(item,dict) and item.get('pid')==service_match['pid']
                and item.get('start_ticks')==service_match['start_ticks']
                and item.get('pid_namespace')==supervisor_identity.get('pid_namespace') for item in chain))
    if links_valid:
        allowed={'MATCHED','NAMESPACE_ALIAS','NO_SERVICE_ANCESTOR'}
        for link in links:
            if not isinstance(link,dict):links_valid=False;break
            key=(link.get('gpu_pid'),link.get('gpu_uuid'))
            classification=link.get('classification')
            identity=link.get('proc_identity')
            if (type(key[0]) is not int or key[0]<=1 or not isinstance(key[1],str)):
                links_valid=False;break
            local=process_by_pid.get(identity.get('pid')) if isinstance(identity,dict) else None
            nspid=identity.get('nspid') if isinstance(identity,dict) else None
            namespaces={'pid':'pid_namespace','mnt':'mnt_namespace','cgroup':'cgroup_namespace'}
            identity_matches=(isinstance(identity,dict) and isinstance(local,dict)
                and type(identity.get('pid')) is int and identity['pid']>1
                and type(identity.get('start_ticks')) is int and identity['start_ticks']>0
                and isinstance(nspid,list) and nspid and key[0] in nspid
                and identity.get('nspid_available') is True and identity.get('identity_state')=='VERIFIED'
                and local.get('start_ticks')==identity.get('start_ticks') and local.get('nspid')==nspid
                and local.get('comm')==identity.get('comm')
                and isinstance(local.get('namespaces'),dict)
                and all(local['namespaces'].get(ns)==identity.get(field) for ns,field in namespaces.items()))
            visibility_matches=((classification=='NAMESPACE_ALIAS' and link.get('visibility')=='NSPID_ALIAS'
                                  and isinstance(identity,dict) and identity.get('pid')!=key[0])
                or (classification in ('MATCHED','NO_SERVICE_ANCESTOR')
                    and link.get('visibility')=='DIRECT_PROC' and isinstance(identity,dict)
                    and identity.get('pid')==key[0]))
            if (key in observed_links or key not in expected_links
                    or link.get('evidence_state')!='COMPLETE'
                    or classification not in allowed
                    or link.get('identity_stability') not in ('STABLE_BOTH','POST_ONLY')
                    or ((link.get('inventory_presence')=='BOTH') != (link.get('identity_stability')=='STABLE_BOTH'))
                    or link.get('inventory_presence') not in ('BOTH','AFTER_ONLY')
                    or not identity_matches or not visibility_matches
                    or not service_link_valid(link,classification)):
                links_valid=False;break
            observed_links.add(key)
    gpu_complete=(gpu_inventory_valid(before) and gpu_inventory_valid(after)
        and links_valid and observed_links==expected_links)
    if supervisor_complete and supervisor_services:
        running_services=[service for service in supervisor_services
            if isinstance(service,dict) and service.get('state')=='RUNNING']
        for service in running_services:
            identity=service.get('identity')
            local=process_by_pid.get(service.get('pid'))
            if (not isinstance(identity,dict) or not isinstance(local,dict)
                    or identity.get('pid')!=service.get('pid')
                    or identity.get('start_ticks')!=local.get('start_ticks')
                    or identity.get('nspid')!=local.get('nspid')
                    or identity.get('comm')!=local.get('comm')
                    or not isinstance(local.get('namespaces'),dict)
                    or any(local['namespaces'].get(ns)!=identity.get(field)
                           for ns,field in (('pid','pid_namespace'),('mnt','mnt_namespace'),('cgroup','cgroup_namespace')))):
                supervisor_complete=False
    statuses=bundle.get('worker_sections',[]) if isinstance(bundle,dict) else []
    required_workers_complete=(isinstance(statuses,list)
        and {row.get('section') for row in statuses if isinstance(row,dict)}>=set(('hardware','process_rows','supervisor'))
        and all(next((row.get('status')=='PRESENT' for row in statuses
                      if isinstance(row,dict) and row.get('section')==name),False)
                for name in ('hardware','process_rows','supervisor')))
    return {'worker_records_complete':required_workers_complete,
            'process_census_complete':process_complete,
            'supervisor_inventory_complete':supervisor_complete,
            'supervisor_crosscheck_complete':crosscheck_complete,
            'supervisor_command_rc':service_rc,
            'supervisor_command_success':services.get('command_success') if isinstance(services,dict) else None,
            'supervisor_service_health':service_health,
            'gpu_census_complete':gpu_complete,
            'process_row_count':process.get('row_count') if isinstance(process,dict) else None,
            'process_rows_sha256':process.get('rows_sha256') if isinstance(process,dict) else None,
            'gpu_link_count':len(links) if isinstance(links,list) else None,
            'gpu_pid_reconciliation':[{'gpu_pid':link.get('gpu_pid'),'gpu_uuid':link.get('gpu_uuid'),
                'classification':link.get('classification'),'evidence_state':link.get('evidence_state'),
                'visibility':link.get('visibility'),'identity_stability':link.get('identity_stability')}
                for link in links if isinstance(link,dict)] if isinstance(links,list) else None}

def require_audit_census_complete(stdout):
    gate=audit_census_status(stdout)
    if not (gate['worker_records_complete'] and gate['process_census_complete']
            and gate['supervisor_inventory_complete'] and gate['supervisor_crosscheck_complete']
            and gate['gpu_census_complete']):
        raise RuntimeError('HOLD_AUDIT_CENSUS_INCOMPLETE')
    return gate

def _has_exact_terminal_completion_marker(stdout,marker):
    """Accept one exact completion line only after all remote NOX payload lines."""
    lines=stdout.splitlines()
    matches=[index for index,line in enumerate(lines) if line==marker]
    if len(matches)!=1:return False
    marker_index=matches[0]
    return not any(line.startswith('NOX_MAINT_') and index>marker_index
                   for index,line in enumerate(lines))

def forward_remote_stdout(stdout,action,request_id,source_sha):
    """Return only bounded marker lines; oversized audit records become a verified bundle."""
    if action=='source_attest':return forward_source_attestation_stdout(stdout)[0]
    lines=stdout.splitlines();forwarded=[];audit_bundle=None
    if action=='audit':
        audit_bundle=audit_bundle_line(stdout)
        bundle_records=build_transfer_records(audit_bundle,request_id,source_sha,force=True)
        if reassemble_transfer_records(bundle_records,request_id,source_sha)!=audit_bundle.encode('utf-8'):
            raise RuntimeError('HOLD_AUDIT_BUNDLE_REASSEMBLY')
    for line in lines:
        if not line.startswith('NOX_MAINT_'):continue
        if action=='audit':
            if line.startswith(AUDIT_PREFIX):continue
            if line==AUDIT_COMPLETE:
                forwarded.extend(bundle_records)
                forwarded.append('NOX_MAINT_AUDIT_WORKERS_COMPLETE=true')
                continue
            raise RuntimeError('HOLD_REMOTE_MARKER_NOT_ALLOWLISTED')
        if action=='inspect' and len(line)>=MAX_FORWARD_LINE_CHARS:
            raise RuntimeError('HOLD_REMOTE_INSPECT_MARKER_OVERSIZE')
        _validate_forward_marker(action,line)
        if len(line)>=MAX_FORWARD_LINE_CHARS:
            raise RuntimeError('HOLD_REMOTE_MARKER_OVERSIZE_UNVERIFIED')
        forwarded.append(line)
    if action=='audit' and not any(line=='NOX_MAINT_AUDIT_WORKERS_COMPLETE=true' for line in forwarded):
        raise RuntimeError('HOLD_AUDIT_WORKERS_COMPLETE_MARKER_MISSING')
    return forwarded

SOURCE_ATTEST_MARKER='NOX_MAINT_SOURCE_ATTESTATION='
SOURCE_ATTEST_COMPLETE_TRUE='NOX_MAINT_SOURCE_ATTESTATION_COMPLETE=true'
SOURCE_ATTEST_COMPLETE_FALSE='NOX_MAINT_SOURCE_ATTESTATION_COMPLETE=false'
SOURCE_ATTEST_SCHEMA='NOX_CHAT_S03_SOURCE_ATTESTATION_V1'
SOURCE_ATTEST_MAX_LINE_BYTES=64*1024
SOURCE_ATTEST_IDENT_RE=re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,79}$')
SOURCE_ATTEST_SECRET_NAME_RE=re.compile(
    r'(?:secret|password|credential|(?:api|access|private|auth)[_-]?key|(?:access|auth)[_-]?token)', re.I)
SOURCE_ATTEST_HASH_RE=re.compile(r'^[0-9a-f]{64}$')
SOURCE_ATTEST_GUARANTEES={
    'target_paths_fixed':True, 'target_modules_imported':False,
    'target_code_executed':False, 'subprocesses_run':False,
    'database_opened':False, 'chat_rows_read':False,
    'source_text_emitted':False, 'source_literals_emitted':False,
}


def _source_attest_hold():
    raise RuntimeError('HOLD_SOURCE_ATTESTATION_REPORT_SCHEMA')


def _source_attest_int(value,maximum=(1<<63)-1):
    if type(value) is not int or value < 0 or value > maximum:_source_attest_hold()


def _source_attest_bool(value):
    if type(value) is not bool:_source_attest_hold()


def _source_attest_ident(value):
    if (not isinstance(value,str) or not SOURCE_ATTEST_IDENT_RE.fullmatch(value)
            or SOURCE_ATTEST_SECRET_NAME_RE.search(value)):_source_attest_hold()


def _source_attest_qualname(value,module=False):
    if module and value=='<module>':return
    if not isinstance(value,str) or len(value)>200:_source_attest_hold()
    for part in value.split('.'):_source_attest_ident(part)


def _source_attest_hash(value):
    if not isinstance(value,str) or not SOURCE_ATTEST_HASH_RE.fullmatch(value):_source_attest_hold()


def _source_attest_signature(row):
    keys={'qualname','async','posonly','posonly_has_default','positional','positional_has_default',
          'vararg','kwonly','kwonly_required','kwarg','argument_annotations_present',
          'return_annotation_present','positional_default_count','kwonly_default_count',
          'candidate_reasons','return_none_count','return_value_count','commit_call',
          'rollback_call','context_manager_count','function_ast_sha256'}
    if not isinstance(row,dict) or set(row)!=keys:_source_attest_hold()
    _source_attest_qualname(row['qualname'])
    for key in ('async','argument_annotations_present','return_annotation_present','commit_call','rollback_call'):
        _source_attest_bool(row[key])
    if '.' not in row['qualname'] and row['qualname'].startswith('UNSAFE_'):_source_attest_hold()
    for names_key,defaults_key in (('posonly','posonly_has_default'),('positional','positional_has_default'),
                                   ('kwonly','kwonly_required')):
        names=row[names_key];flags=row[defaults_key]
        if not isinstance(names,list) or not isinstance(flags,list) or len(names)!=len(flags) or len(names)>128:
            _source_attest_hold()
        for name in names:_source_attest_ident(name)
        for flag in flags:_source_attest_bool(flag)
    for key in ('vararg','kwarg'):
        if row[key] is not None:_source_attest_ident(row[key])
    reasons=row['candidate_reasons']
    if (not isinstance(reasons,list) or not reasons or len(reasons)>2
            or any(not isinstance(item,str) or item not in ('writer_name','s03_table_dml')
                   for item in reasons)
            or len(set(reasons))!=len(reasons)):
        _source_attest_hold()
    for key in ('positional_default_count','kwonly_default_count','return_none_count',
                'return_value_count','context_manager_count'):_source_attest_int(row[key],100000)
    if row['positional_default_count'] != (sum(row['posonly_has_default'])+sum(row['positional_has_default'])):
        _source_attest_hold()
    if row['kwonly_default_count'] != sum(not flag for flag in row['kwonly_required']):
        _source_attest_hold()
    _source_attest_hash(row['function_ast_sha256'])


def _source_attest_target(row,label,relative):
    common={'target','relative_path','status'}
    metadata={'bytes','uid','gid','mode','mtime_ns','ctime_ns','file_identity_sha256','sha256'}
    ast_fields={'ast_node_count','source_text_emitted','source_literals_emitted'}
    chat_fields={'imports','imports_truncated','call_sites','call_sites_truncated',
                 'dynamic_access_detected','static_scope_complete'}
    memory_fields={'writer_signatures','writer_signature_count'}
    if not isinstance(row,dict) or not common.issubset(row):_source_attest_hold()
    if row['target']!=label or row['relative_path']!=relative:_source_attest_hold()
    status=row['status']
    if not isinstance(status,str) or (status!='AST_PARSED' and not re.fullmatch(r'HOLD_[A-Z0-9_]{1,64}',status)):
        _source_attest_hold()
    allowed=common|metadata|ast_fields|(chat_fields if label=='chat_proxy' else memory_fields)
    if not set(row).issubset(allowed):_source_attest_hold()
    for key in ('bytes','uid','gid','mtime_ns','ctime_ns'):
        if key in row:_source_attest_int(row[key],1<<63)
    if 'bytes' in row and row['bytes']>1024*1024:_source_attest_hold()
    if 'mode' in row and (not isinstance(row['mode'],str) or not re.fullmatch(r'[0-7]{4}',row['mode'])):
        _source_attest_hold()
    for key in ('file_identity_sha256','sha256'):
        if key in row:_source_attest_hash(row[key])
    if 'ast_node_count' in row:_source_attest_int(row['ast_node_count'],100000)
    for key in ('source_text_emitted','source_literals_emitted'):
        if key in row and row[key] is not False:_source_attest_hold()
    if status=='AST_PARSED':
        required=common|metadata|ast_fields|(chat_fields if label=='chat_proxy' else memory_fields)
        if set(row)!=required:_source_attest_hold()
        if row['bytes']<0 or row['ast_node_count']<1:_source_attest_hold()
        if row['source_text_emitted'] is not False or row['source_literals_emitted'] is not False:
            _source_attest_hold()
        if label=='chat_proxy':
            for key in ('imports_truncated','call_sites_truncated','dynamic_access_detected','static_scope_complete'):
                _source_attest_bool(row[key])
            imports=row['imports'];calls=row['call_sites']
            if not isinstance(imports,list) or len(imports)>32 or not isinstance(calls,list) or len(calls)>64:
                _source_attest_hold()
            for item in imports:
                if not isinstance(item,dict):_source_attest_hold()
                if item.get('kind')=='module' and set(item)=={'kind','alias'}:
                    _source_attest_ident(item['alias'])
                elif item.get('kind')=='symbol' and set(item)=={'kind','symbol','alias'}:
                    _source_attest_ident(item['symbol']);_source_attest_ident(item['alias'])
                else:_source_attest_hold()
            for item in calls:
                if (not isinstance(item,dict) or set(item)!={'caller','symbol','kind'}
                        or item['kind'] not in ('module_attribute','imported_symbol')):_source_attest_hold()
                _source_attest_qualname(item['caller'],module=True);_source_attest_ident(item['symbol'])
        else:
            rows=row['writer_signatures']
            if not isinstance(rows,list) or len(rows)>48:_source_attest_hold()
            _source_attest_int(row['writer_signature_count'],48)
            if row['writer_signature_count']!=len(rows):_source_attest_hold()
            for signature in rows:_source_attest_signature(signature)
    elif 'writer_signatures' in row or 'imports' in row or 'call_sites' in row:
        _source_attest_hold()


def validate_source_attestation_report(report):
    """Accept only the fixed AST receipt schema; reject unknown or secret-like fields."""
    if not isinstance(report,dict) or report.get('schema')!=SOURCE_ATTEST_SCHEMA:
        _source_attest_hold()
    _source_attest_bool(report.get('complete'))
    status=report.get('status')
    if not isinstance(status,str):_source_attest_hold()
    if set(report)=={'schema','status','complete'}:
        if report['complete'] or not re.fullmatch(r'HOLD_[A-Z0-9_]{1,64}',status):_source_attest_hold()
        return report
    full_keys={'schema','status','complete','targets','chat_to_s03_writer_links','guarantees'}
    short_oversize={'schema','status','complete','targets','guarantees'}
    if set(report) not in (full_keys,short_oversize):_source_attest_hold()
    if status not in ('SOURCE_STATIC_ATTESTED','HOLD_STATIC_WRITER_LINK_INCOMPLETE') \
            and not re.fullmatch(r'HOLD_[A-Z0-9_]{1,64}',status):_source_attest_hold()
    targets=report['targets']
    if not isinstance(targets,list) or len(targets) not in (0,2):_source_attest_hold()
    if set(report)==short_oversize:
        if report['complete'] or status!='HOLD_REPORT_OVERSIZED' or targets:_source_attest_hold()
    elif not targets:
        _source_attest_hold()
    if targets:
        _source_attest_target(targets[0],'chat_proxy','scripts/chat_proxy.py')
        _source_attest_target(targets[1],'s03_memory','scripts/s03_memory.py')
    guarantees=report['guarantees']
    if not isinstance(guarantees,dict) or set(guarantees)!=set(SOURCE_ATTEST_GUARANTEES):
        _source_attest_hold()
    for key,expected in SOURCE_ATTEST_GUARANTEES.items():
        if type(guarantees[key]) is not bool or guarantees[key] is not expected:_source_attest_hold()
    if report['complete']:
        if set(report)!=full_keys or status!='SOURCE_STATIC_ATTESTED' or len(targets)!=2:_source_attest_hold()
        proxy,memory=targets
        if (proxy['status']!='AST_PARSED' or memory['status']!='AST_PARSED'
                or not proxy['static_scope_complete'] or proxy['imports_truncated']
                or proxy['call_sites_truncated']):
            _source_attest_hold()
        calls={row['symbol'] for row in proxy['call_sites']}
        writers={row['qualname'] for row in memory['writer_signatures'] if '.' not in row['qualname']}
        expected=[row for row in memory['writer_signatures']
                  if '.' not in row['qualname'] and row['qualname'] in calls]
        links=report['chat_to_s03_writer_links']
        if not expected or links!=expected or not calls.intersection(writers):_source_attest_hold()
    else:
        if status=='SOURCE_STATIC_ATTESTED':_source_attest_hold()
        if set(report)==full_keys:
            links=report['chat_to_s03_writer_links']
            if not isinstance(links,list) or len(links)>48:_source_attest_hold()
            for signature in links:_source_attest_signature(signature)
            if len(targets)==2 and all(row.get('status')=='AST_PARSED' for row in targets):
                proxy,memory=targets
                calls={row['symbol'] for row in proxy['call_sites']}
                expected=[row for row in memory['writer_signatures']
                          if '.' not in row['qualname'] and row['qualname'] in calls]
                if links!=expected:_source_attest_hold()
        elif targets:
            _source_attest_hold()
    return report


def _source_attest_json(payload):
    def no_duplicate_keys(pairs):
        value={}
        for key,item in pairs:
            if key in value:_source_attest_hold()
            value[key]=item
        return value
    def reject_constant(_value):_source_attest_hold()
    try:
        report=json.loads(payload,object_pairs_hook=no_duplicate_keys,parse_constant=reject_constant)
    except RuntimeError:
        raise
    except (ValueError,TypeError,RecursionError):
        _source_attest_hold()
    return validate_source_attestation_report(report)


def forward_source_attestation_stdout(stdout):
    """Validate and forward exactly the report and its terminal marker."""
    if not isinstance(stdout,str):_source_attest_hold()
    lines=stdout.splitlines()
    if len(lines)!=2 or not lines[0].startswith(SOURCE_ATTEST_MARKER) \
            or lines[1] not in (SOURCE_ATTEST_COMPLETE_TRUE,SOURCE_ATTEST_COMPLETE_FALSE):
        _source_attest_hold()
    if len(lines[0].encode('utf-8'))>SOURCE_ATTEST_MAX_LINE_BYTES:_source_attest_hold()
    report=_source_attest_json(lines[0][len(SOURCE_ATTEST_MARKER):])
    if report['complete'] != (lines[1]==SOURCE_ATTEST_COMPLETE_TRUE):_source_attest_hold()
    if report['complete'] and report['status']!='SOURCE_STATIC_ATTESTED':_source_attest_hold()
    return lines,report


SCOPED_REPAIR_BUNDLES={'nox-control/systemic_relay_20261118/owner_chat_policy_live_smoke_entry.py': (), 'nox-control/systemic_relay_20261118/owner_chat_policy_live_smoke.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_counter_reconcile_policy_v1/owner_chat_counter_policy_entry.py': (), 'nox-control/systemic_relay_20261118/next_reviewed_merge_20261118/prepared_v3/owner_systemic_reviewed_merge_embedded_entry.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_v5/owner_chat_decomposition_embedded_entry.py': (), 'nox-control/owner_continuous_executor_install.py': ('cw_test_nox_forge_language_task_coverage.py', 'cw_test_nox_readonly_retry_backoff.py', 'cw_test_nox_warm_cache_limit_contract.py', 'cw_contract_510dbdec4dd2538ebeac.json', 'cw_contract_9efad5217ab0e554a383.json', 'cw_contract_683c5086d66e750d4ed1.json', 'continuous_transaction_helpers.py', 'continuous_dispatcher.py', 'continuous_planner.py', 'continuous_truth.py'), 'nox-control/owner_bounded_cpu_install.py': ('bc_runtime_d5fb476f53e64d2014f2.py', 'bc_runtime_6c67e567e669b993d016.py', 'bc_runtime_2c83ec53f7ee7c2d76bc.py', 'bc_runtime_294473d35d4870f50467.py'), 'nox-control/owner_project_runtime_update.py': ('ru_runtime_fcb77cc59eb9a88dde68.py', 'ru_runtime_84d54c647b0a63447aca.py', 'ru_runtime_52e62a143d16f387899f.py', 'ru_runtime_aa0dd1c8266106b599ce.py', 'ru_plans_a171fa7a94084a1f4b67.data', 'ru_blobs_fa3d69e506d727295094.data', 'ru_plans_79b77425ff05d3337c2e.data', 'ru_blobs_b980a61884965f4838f8.data', 'ru_plans_dd24421576ae4160fa01.data', 'ru_blobs_7e625acddd71fe95988e.data', 'ru_blobs_4b06687bbad8fe6ab046.data', 'ru_contracts_eece310e5608fa9c633d.data'), 'nox-control/owner_complete_executor_install.py': ('ce_runtime_2c4735938dacd2a062ed.py', 'ce_runtime_71dd03dee52f1673c297.py', 'ce_runtime_f6b2f98ac5c7c291ffef.py', 'ce_runtime_687ea3b3548badf9b7ba.py', 'ce_runtime_35b0e94f9c883da017e4.py', 'ce_runtime_d0ff44d4752128c26779.py', 'ce_runtime_119115603be6dba84121.py', 'ce_runtime_7f18d69529582b65f7b8.py', 'ce_runtime_126c77c1281b74676930.py', 'ce_runtime_485d4a4a571c434afb98.py', 'ce_baseline_bb2c543979ad58801d97.source', 'ce_baseline_4d1274059d034bb9b96a.source', 'ce_baseline_d9ec6a8250a167d774ba.source', 'ce_baseline_c676fdda4fa47d316eb1.source', 'ce_baseline_8657ad367e6dd25b48ca.source', 'ce_baseline_006fc038f43682fa36d2.source', 'ce_baseline_d35064a3fc5707dfc174.source', 'ce_baseline_66a6617d6f582876dbdc.source', 'ce_baseline_e3b0c44298fc1c149afb.source', 'ce_baseline_092db7d32a048c1706da.source', 'ce_baseline_dc19594b45a7fae32bf9.source', 'ce_baseline_b4ece67144248808a12c.source', 'ce_baseline_21f8538fec15d39b4dbc.source', 'ce_baseline_3efe025681c3a54cbfac.source', 'ce_baseline_b3c5d26011400b110a1b.source', 'ce_baseline_f299d32099c25ea1822c.source', 'ce_baseline_0fff97b7e758e3e43073.source', 'ce_baseline_fd815f9a743bfcdf6e71.source', 'ce_baseline_97c433b8893514f5812b.source', 'ce_baseline_fc5d6c564c651c2abc81.source', 'ce_baseline_623bfb4ba2d28d3dd3db.source', 'ce_baseline_9201bc3629682a577c80.source', 'ce_baseline_d6042e38549360ace8f9.source', 'ce_baseline_2860173d8d6ed7147af2.source', 'ce_baseline_970d6681ce5dc57156e2.source', 'ce_baseline_6aa9265942695d2b54b3.source', 'ce_baseline_8d2070c2f0819e7d1c2b.source', 'ce_baseline_60e28219f670a8449a56.source', 'ce_plans_283ff826ba1180398888.json', 'ce_blobs_fa3d69e506d727295094.source', 'ce_plans_e7c99335a4a790202f22.json', 'ce_blobs_f7b69405224c63868b76.source', 'ce_plans_de41f4de77a043c695fe.json', 'ce_blobs_7e625acddd71fe95988e.source', 'ce_plans_67e819b4ff1b94cc5bdd.json', 'ce_blobs_b980a61884965f4838f8.source', 'ce_plans_4037501920f2e9f3ea41.json', 'ce_blobs_06940cb13bd568d4cfaa.source', 'ce_plans_9b80e2075b52602ac9e1.json', 'ce_blobs_f336c58fb5062aec6d5b.source', 'ce_contracts_b40696685ca2b7c848a2.json', 'ce_manifests_79a8efb2d344479471bd.json', 'ce_manifests_e040c40bd8ee3d29b0cc.json'), 'nox-control/owner_post_reset_state_observe.py': (), 'nox-control/owner_chat_markdown_asset_install_v2.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'nox-v24-chat-markdown-final.js'), 'nox-control/owner_chat_markdown_metadata.py': (), 'nox-control/owner_chat_markdown_asset_install.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'nox-v24-chat-markdown-final.js'), 'nox-control/owner_workspace_browser_acceptance_v6.py': ('owner_workspace_browser_acceptance_v5.py', 'owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_checkpoint_proof_v2.py': (), 'nox-control/owner_workspace_browser_acceptance_v5.py': ('owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_chat_markdown_acceptance.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_memfd_progress.py': (), 'nox-control/owner_qwen_successor_checkpoint_proof.py': (), 'nox-control/owner_qwen_successor_observe_v2.py': (), 'nox-control/owner_workspace_browser_acceptance_v3.py': ('owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_entry_v2.py': ('owner_qwen_successor_install_v2.py', 'owner_qwen_execution_successor.py', 'qwen_student_training_entry_successor.py', 'owner_qwen_successor_guard.py', 'owner_qwen_successor_status.py', 'owner_qwen_successor_media_handoff.py', 'owner_qwen_successor_media_guard.py', 'owner_qwen_successor_handback_retry.py', 'owner_qwen_successor_hermes_hydrate.py', 'owner_qwen_successor_watch.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_workspace_browser_acceptance_v2.py': ('owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_entry.py': ('owner_qwen_successor_install.py', 'owner_qwen_execution_successor.py', 'qwen_student_training_entry_successor.py', 'owner_qwen_successor_guard.py', 'owner_qwen_successor_status.py', 'owner_qwen_successor_media_handoff.py', 'owner_qwen_successor_media_guard.py', 'owner_qwen_successor_handback_retry.py', 'owner_qwen_successor_hermes_hydrate.py', 'owner_qwen_successor_watch.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_workspace_browser_acceptance.py': ('owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_budget_failure_diagnose.py': (), 'nox-control/owner_workspace_asset_install.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'workspace-owner-capabilities.js'), 'nox-control/owner_qwen_public_memfd_access_probe.py': (), 'nox-control/owner_training_control_readonly_batch.py': ('owner_qwen_transport_budget_observe.py', 'owner_admin_control_structure_probe.py', 'owner_qwen_public_memfd_access_probe.py'), 'nox-control/owner_qwen_transport_budget_observe.py': (), 'nox-control/owner_admin_control_structure_probe.py': (), 'nox-control/owner_qwen_transport_budget_finalize_6914959637.py': (), 'nox-control/owner_chat_page_diagnose.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_chat_action_routing_install.py': ('owner_chat_stream_action_routing.py', 'owner_download_status_entry.py', 'owner_native_repair.py'), 'nox-control/owner_chat_plan_api_probe.py': (), 'nox-control/owner_chat_stream_asset_install_v2.py': ('nox-v135-resonance-owner-bridge-coalesced.js', 'owner_media_acceptance_entry.py', 'owner_native_repair.py'), 'nox-control/owner_qwen_transport_rollback_entry.py': ('owner_qwen_transport_rollback.py', 'owner_qwen_transport_revision_install.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py', 'owner_qwen_transport_failed_diagnostic.json'), 'nox-control/owner_qwen_transport_budget_entry.py': ('owner_qwen_revision_install.py', 'qwen_student_training_entry_revision.py', 'owner_qwen_transport_budget_install.py', 'qwen_student_training_entry_transport_budget.py', 'owner_qwen_execution_revision.py', 'owner_qwen_revision_guard.py', 'owner_qwen_revision_status.py', 'owner_qwen_revision_media_handoff.py', 'owner_qwen_revision_media_guard.py', 'owner_qwen_revision_handback_retry.py', 'owner_hermes_revision_hydrate.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_chat_stream_asset_install.py': ('nox-v135-resonance-owner-bridge-coalesced.js', 'owner_media_acceptance_entry.py', 'owner_native_repair.py'), 'nox-control/owner_browser_asset_identity_entry.py': ('owner_browser_normal_motion_entry.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py', 'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py', 'owner_chat_normal_motion_qa.py', 'owner_chat_asset_identity_qa.py'), 'nox-control/owner_qwen_held_media_smoke_v2_entry.py': ('owner_qwen_held_media_smoke_v2.py', 'owner_media_acceptance_entry.py', 'owner_qwen_revision_install.py', 'owner_native_repair.py', 'owner_download_status_entry.py'), 'nox-control/owner_browser_normal_motion_entry.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py', 'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py', 'owner_chat_normal_motion_qa.py'), 'nox-control/owner_qwen_held_media_smoke_entry.py': ('owner_qwen_held_media_smoke.py', 'owner_media_acceptance_entry.py', 'owner_qwen_revision_install.py', 'owner_native_repair.py', 'owner_download_status_entry.py'), 'nox-control/owner_qwen_transport_install_entry.py': ('owner_qwen_revision_install.py', 'qwen_student_training_entry_revision.py', 'owner_qwen_transport_revision_install.py', 'qwen_student_training_entry_transport_candidate.py', 'owner_qwen_execution_revision.py', 'owner_qwen_revision_guard.py', 'owner_qwen_revision_status.py', 'owner_qwen_revision_media_handoff.py', 'owner_qwen_revision_media_guard.py', 'owner_qwen_revision_handback_retry.py', 'owner_hermes_revision_hydrate.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_reviewed_rescue_catalog_append.py': ('rv_plan_379d1c5b50e42fb50165ce1fbe904cf47b1b45b3747878c60f9b1208d6e13e23.json', 'rv_payload_5201af0115e1ead68d3369794e33bbc97d7b7b2f00762c5c2ecfdaa7dda45926.source', 'rv_payload_4329f7389b24cfbb1fbb47c91b43eb7407bf18c95d15064fc7ea8166cde0a821.source'), 'nox-control/owner_kernel_self_fd_install.py': ('sf_runtime_192d0c1b7b87447d4f08.py', 'sf_plan_457dbaf4484cfb5b7e14.json', 'sf_payload_5201af0115e1ead68d33.source', 'sf_payload_4329f7389b24cfbb1fbb.source', 'sf_fd_descriptor_768d28516014a124a380.json'), 'nox-control/owner_reviewed_proc_followup_catalog_append.py': ('fu_plan_3f620116ee563127d7e94bfeac7aae1408aaa4f1752f431fee774c49023e6509.json', 'fu_payload_a71051c085f8bfdbeda93f3f4c16501444ca35942ac4ca7f3a46d7bd16acfbbc.source', 'fu_payload_f5c8eb6b42e71efa38745bc6f729a989b4a199999d7c3b9aa45cebbde36f851a.source'), 'nox-control/owner_model_slot_recovery.py': ('slot_contract_3f43e152774c159bbe45.json', 'slot_contract_60a6abf6691f6c3fb186.json', 'slot_transaction_helpers.py', 'slot_model_client.py'), 'nox-control/owner_c02_memory_progress_install.py': ('c02_contract_4a8f20c371f3211c2351.json', 'c02_test_nox_c02_existing_cognition.py', 'c02_test_nox_c02_optional_starvation.py', 'c02_transaction_helpers.py'), 'nox-control/owner_c02_memory_reviewed_recovery.py': ('c02r_payload_b504248ac1ae4a093382.source', 'c02r_plan_5d05ba50d058981ce8ba.json', 'c02r_transaction_helpers.py'), 'nox-control/systemic_relay_20261118/owner_systemic_relay_entry.py': ('systemic_owner_subagent_dispatcher.py', 'systemic_owner_subagent_processes.py', 'systemic_owner_project_native.py', 'systemic_owner_project_planner.py', 'systemic_owner_subagent_instruction_truth.py', 'systemic_owner_systemic_refill.py', 'systemic_transaction_helpers.py', 'systemic_cache_fill_ttl.json', 'systemic_forge_read_budget.json', 'systemic_relay_manifest.json', 'systemic_skill_journal_budget.json'), 'nox-control/systemic_relay_20261118/owner_eval_checkpoint_prepare.py': (), 'nox-control/systemic_relay_20261118/owner_systemic_reviewed_entry.py': ('reviewed_systemic_transaction_helpers.py', 'reviewed_cache_ttl_plan.json', 'reviewed_cache_ttl_payload.source', 'reviewed_forge_budget_plan.json', 'reviewed_forge_budget_payload.source', 'reviewed_skill_budget_plan.json', 'reviewed_skill_budget_payload.source'), 'nox-control/systemic_relay_20261118/next_pack_44368502183/package/native_publish_entry_d58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212.py': (), 'nox-control/systemic_relay_20261118/tooling/owner_nox_acceleration_entry.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_v4/owner_chat_decomposition_embedded_entry.py': ()}
SCOPED_REPAIR_EXTRA_PATHS={'nox-control/owner_continuous_executor_install.py': ('nox-control/continuous_executor_20261118/assets/cw_test_nox_forge_language_task_coverage.py', 'nox-control/continuous_executor_20261118/assets/cw_test_nox_readonly_retry_backoff.py', 'nox-control/continuous_executor_20261118/assets/cw_test_nox_warm_cache_limit_contract.py', 'nox-control/continuous_executor_20261118/assets/cw_contract_510dbdec4dd2538ebeac.json', 'nox-control/continuous_executor_20261118/assets/cw_contract_9efad5217ab0e554a383.json', 'nox-control/continuous_executor_20261118/assets/cw_contract_683c5086d66e750d4ed1.json', 'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py', 'nox-control/continuous_executor_20261118/assets/continuous_dispatcher.py', 'nox-control/continuous_executor_20261118/assets/continuous_planner.py', 'nox-control/continuous_executor_20261118/assets/continuous_truth.py'), 'nox-control/owner_bounded_cpu_install.py': ('nox-control/complete_executor_budget_20261118/assets/bc_runtime_d5fb476f53e64d2014f2.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_6c67e567e669b993d016.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_2c83ec53f7ee7c2d76bc.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_294473d35d4870f50467.py'), 'nox-control/owner_project_runtime_update.py': ('nox-control/complete_executor_retries_20261118/assets/ru_runtime_fcb77cc59eb9a88dde68.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_84d54c647b0a63447aca.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_52e62a143d16f387899f.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_aa0dd1c8266106b599ce.py', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_a171fa7a94084a1f4b67.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_fa3d69e506d727295094.data', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_79b77425ff05d3337c2e.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_b980a61884965f4838f8.data', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_dd24421576ae4160fa01.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_7e625acddd71fe95988e.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_4b06687bbad8fe6ab046.data', 'nox-control/complete_executor_retries_20261118/assets/ru_contracts_eece310e5608fa9c633d.data'), 'nox-control/owner_complete_executor_install.py': ('nox-control/complete_executor_20261118/assets/ce_runtime_2c4735938dacd2a062ed.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_71dd03dee52f1673c297.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_f6b2f98ac5c7c291ffef.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_687ea3b3548badf9b7ba.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_35b0e94f9c883da017e4.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_d0ff44d4752128c26779.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_119115603be6dba84121.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_7f18d69529582b65f7b8.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_126c77c1281b74676930.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_485d4a4a571c434afb98.py', 'nox-control/complete_executor_20261118/assets/ce_baseline_bb2c543979ad58801d97.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_4d1274059d034bb9b96a.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d9ec6a8250a167d774ba.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_c676fdda4fa47d316eb1.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_8657ad367e6dd25b48ca.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_006fc038f43682fa36d2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d35064a3fc5707dfc174.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_66a6617d6f582876dbdc.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_e3b0c44298fc1c149afb.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_092db7d32a048c1706da.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_dc19594b45a7fae32bf9.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_b4ece67144248808a12c.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_21f8538fec15d39b4dbc.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_3efe025681c3a54cbfac.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_b3c5d26011400b110a1b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_f299d32099c25ea1822c.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_0fff97b7e758e3e43073.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_fd815f9a743bfcdf6e71.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_97c433b8893514f5812b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_fc5d6c564c651c2abc81.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_623bfb4ba2d28d3dd3db.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_9201bc3629682a577c80.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d6042e38549360ace8f9.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_2860173d8d6ed7147af2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_970d6681ce5dc57156e2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_6aa9265942695d2b54b3.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_8d2070c2f0819e7d1c2b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_60e28219f670a8449a56.source', 'nox-control/complete_executor_20261118/assets/ce_plans_283ff826ba1180398888.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_fa3d69e506d727295094.source', 'nox-control/complete_executor_20261118/assets/ce_plans_e7c99335a4a790202f22.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_f7b69405224c63868b76.source', 'nox-control/complete_executor_20261118/assets/ce_plans_de41f4de77a043c695fe.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_7e625acddd71fe95988e.source', 'nox-control/complete_executor_20261118/assets/ce_plans_67e819b4ff1b94cc5bdd.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_b980a61884965f4838f8.source', 'nox-control/complete_executor_20261118/assets/ce_plans_4037501920f2e9f3ea41.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_06940cb13bd568d4cfaa.source', 'nox-control/complete_executor_20261118/assets/ce_plans_9b80e2075b52602ac9e1.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_f336c58fb5062aec6d5b.source', 'nox-control/complete_executor_20261118/assets/ce_contracts_b40696685ca2b7c848a2.json', 'nox-control/complete_executor_20261118/assets/ce_manifests_79a8efb2d344479471bd.json', 'nox-control/complete_executor_20261118/assets/ce_manifests_e040c40bd8ee3d29b0cc.json'), 'nox-control/owner_chat_markdown_asset_install_v2.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/nox-v24-chat-markdown-final.js'), 'nox-control/owner_chat_markdown_asset_install.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/nox-v24-chat-markdown-final.js'), 'nox-control/owner_workspace_browser_acceptance_v6.py': ('nox-control/owner_workspace_browser_acceptance_v5.py', 'nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_workspace_browser_acceptance_v5.py': ('nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_workspace_browser_acceptance_v3.py': ('nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_qwen_successor_entry_v2.py': ('nox-control/owner_qwen_successor_install_v2.py', 'nox-control/owner_qwen_execution_successor.py', 'nox-control/qwen_student_training_entry_successor.py', 'nox-control/owner_qwen_successor_guard.py', 'nox-control/owner_qwen_successor_status.py', 'nox-control/owner_qwen_successor_media_handoff.py', 'nox-control/owner_qwen_successor_media_guard.py', 'nox-control/owner_qwen_successor_handback_retry.py', 'nox-control/owner_qwen_successor_hermes_hydrate.py', 'nox-control/owner_qwen_successor_watch.py'), 'nox-control/owner_workspace_browser_acceptance_v2.py': ('nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_qwen_successor_entry.py': ('nox-control/owner_qwen_successor_install.py', 'nox-control/owner_qwen_execution_successor.py', 'nox-control/qwen_student_training_entry_successor.py', 'nox-control/owner_qwen_successor_guard.py', 'nox-control/owner_qwen_successor_status.py', 'nox-control/owner_qwen_successor_media_handoff.py', 'nox-control/owner_qwen_successor_media_guard.py', 'nox-control/owner_qwen_successor_handback_retry.py', 'nox-control/owner_qwen_successor_hermes_hydrate.py', 'nox-control/owner_qwen_successor_watch.py'), 'nox-control/owner_workspace_browser_acceptance.py': ('nox-control/owner_chat_page_diagnose.py',), 'nox-control/owner_workspace_asset_install.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/workspace-owner-capabilities.js'), 'nox-control/owner_training_control_readonly_batch.py': ('nox-control/owner_qwen_transport_budget_observe.py', 'nox-control/owner_admin_control_structure_probe.py', 'nox-control/owner_qwen_public_memfd_access_probe.py'), 'nox-control/owner_chat_action_routing_install.py': ('nox-control/owner_chat_stream_action_routing.py',), 'nox-control/owner_chat_stream_asset_install_v2.py': ('coordination/onepass/nox-v135-resonance-owner-bridge-coalesced.js',), 'nox-control/owner_qwen_transport_rollback_entry.py': ('nox-control/owner_qwen_transport_rollback.py', 'nox-control/owner_qwen_transport_revision_install.py', 'nox-control/owner_qwen_transport_failed_diagnostic.json'), 'nox-control/owner_qwen_transport_budget_entry.py': ('nox-control/owner_qwen_transport_budget_install.py', 'nox-control/qwen_student_training_entry_transport_budget.py'), 'nox-control/owner_chat_stream_asset_install.py': ('coordination/onepass/nox-v135-resonance-owner-bridge-coalesced.js',), 'nox-control/owner_browser_asset_identity_entry.py': ('nox-control/owner_browser_normal_motion_entry.py', 'nox-control/owner_chat_normal_motion_qa.py', 'nox-control/owner_chat_asset_identity_qa.py'), 'nox-control/owner_qwen_held_media_smoke_v2_entry.py': ('nox-control/owner_qwen_held_media_smoke_v2.py',), 'nox-control/owner_browser_normal_motion_entry.py': ('nox-control/owner_chat_normal_motion_qa.py',), 'nox-control/owner_qwen_transport_install_entry.py': ('nox-control/owner_qwen_transport_revision_install.py', 'nox-control/qwen_student_training_entry_transport_candidate.py'), 'nox-control/owner_reviewed_rescue_catalog_append.py': ('nox-control/complete_executor_rescue_20261118/assets/rv_plan_379d1c5b50e42fb50165ce1fbe904cf47b1b45b3747878c60f9b1208d6e13e23.json', 'nox-control/complete_executor_rescue_20261118/assets/rv_payload_5201af0115e1ead68d3369794e33bbc97d7b7b2f00762c5c2ecfdaa7dda45926.source', 'nox-control/complete_executor_rescue_20261118/assets/rv_payload_4329f7389b24cfbb1fbb47c91b43eb7407bf18c95d15064fc7ea8166cde0a821.source'), 'nox-control/owner_kernel_self_fd_install.py': ('nox-control/complete_executor_proc_identity_20261118/assets/sf_runtime_192d0c1b7b87447d4f08.py', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_plan_457dbaf4484cfb5b7e14.json', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_payload_5201af0115e1ead68d33.source', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_payload_4329f7389b24cfbb1fbb.source', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_fd_descriptor_768d28516014a124a380.json'), 'nox-control/owner_reviewed_proc_followup_catalog_append.py': ('nox-control/complete_executor_followup_20261118/assets/fu_plan_3f620116ee563127d7e94bfeac7aae1408aaa4f1752f431fee774c49023e6509.json', 'nox-control/complete_executor_followup_20261118/assets/fu_payload_a71051c085f8bfdbeda93f3f4c16501444ca35942ac4ca7f3a46d7bd16acfbbc.source', 'nox-control/complete_executor_followup_20261118/assets/fu_payload_f5c8eb6b42e71efa38745bc6f729a989b4a199999d7c3b9aa45cebbde36f851a.source'), 'nox-control/owner_model_slot_recovery.py': ('nox-control/model_slot_recovery_20261118/assets/slot_contract_3f43e152774c159bbe45.json', 'nox-control/model_slot_recovery_20261118/assets/slot_contract_60a6abf6691f6c3fb186.json', 'nox-control/model_slot_recovery_20261118/assets/slot_transaction_helpers.py', 'nox-control/model_slot_recovery_20261118/assets/slot_model_client.py'), 'nox-control/owner_c02_memory_progress_install.py': ('nox-control/c02_memory_progress_20261118/assets/c02_contract_4a8f20c371f3211c2351.json', 'nox-control/c02_memory_progress_20261118/assets/c02_test_nox_c02_existing_cognition.py', 'nox-control/c02_memory_progress_20261118/assets/c02_test_nox_c02_optional_starvation.py', 'nox-control/c02_memory_progress_20261118/assets/c02_transaction_helpers.py'), 'nox-control/owner_c02_memory_reviewed_recovery.py': ('nox-control/c02_memory_progress_20261118/recovery_assets/c02r_payload_b504248ac1ae4a093382.source', 'nox-control/c02_memory_progress_20261118/recovery_assets/c02r_plan_5d05ba50d058981ce8ba.json', 'nox-control/c02_memory_progress_20261118/recovery_assets/c02r_transaction_helpers.py'), 'nox-control/systemic_relay_20261118/owner_systemic_relay_entry.py': ('nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_dispatcher.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_processes.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_project_native.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_project_planner.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_instruction_truth.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_systemic_refill.py', 'nox-control/systemic_relay_20261118/assets/systemic_transaction_helpers.py', 'nox-control/systemic_relay_20261118/assets/systemic_cache_fill_ttl.json', 'nox-control/systemic_relay_20261118/assets/systemic_forge_read_budget.json', 'nox-control/systemic_relay_20261118/assets/systemic_relay_manifest.json', 'nox-control/systemic_relay_20261118/assets/systemic_skill_journal_budget.json'), 'nox-control/systemic_relay_20261118/owner_eval_checkpoint_prepare.py': (), 'nox-control/systemic_relay_20261118/owner_systemic_reviewed_entry.py': ('nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_systemic_transaction_helpers.py', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_cache_ttl_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_cache_ttl_payload.source', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_forge_budget_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_forge_budget_payload.source', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_skill_budget_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_skill_budget_payload.source')}

FROZEN_BROWSER_PAGE_DEPENDENCIES={
    'owner_browser_stream_only_entry.py':'nox-control/pinned/browser_normal_v1/owner_browser_stream_only_entry.py',
}
SCOPED_REPAIR_BUNDLES[FILES['repair']] = ()
SCOPED_REPAIR_EXTRA_PATHS[FILES['repair']] = ()
SCOPED_REPAIR_BUNDLES[FILES['reflex_successor']] = (
    'owner_systemic_refill.py', 'owner_subagent_dispatcher.py',
    'owner_reflex_taskpack.py', 'continuous_transaction_helpers.py')
SCOPED_REPAIR_EXTRA_PATHS[FILES['reflex_successor']] = (
    'nox-control/systemic_relay_20261118/runtime/owner_systemic_refill.py',
    'nox-control/systemic_relay_20261118/runtime/owner_subagent_dispatcher.py',
    'nox-control/systemic_relay_20261118/runtime/owner_reflex_taskpack.py',
    'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py')
FROZEN_BROWSER_DEPENDENCIES={
    'owner_browser_stream_only_entry.py':'nox-control/pinned/browser_normal_v1/owner_browser_stream_only_entry.py',
    'owner_chat_stream_only_qa.py':'nox-control/pinned/browser_normal_v1/owner_chat_stream_only_qa.py',
}
FROZEN_BROWSER_ENTRIES=('nox-control/owner_browser_normal_motion_entry.py',
                        'nox-control/owner_browser_asset_identity_entry.py')

def repair_bundle_paths(action,entrypoint,paths):
    if action not in ('repair','reflex_successor') or entrypoint not in SCOPED_REPAIR_BUNDLES:return paths
    selected=SCOPED_REPAIR_BUNDLES[entrypoint]
    if len(set(selected))!=len(selected):raise RuntimeError('HOLD_SCOPED_BUNDLE_DUPLICATE_ALLOWLIST')
    overrides=(FROZEN_BROWSER_DEPENDENCIES if entrypoint in FROZEN_BROWSER_ENTRIES else
               FROZEN_BROWSER_PAGE_DEPENDENCIES if entrypoint in ('nox-control/owner_chat_page_diagnose.py',
                   'nox-control/owner_workspace_browser_acceptance.py','nox-control/owner_workspace_browser_acceptance_v2.py','nox-control/owner_workspace_browser_acceptance_v3.py','nox-control/owner_workspace_browser_acceptance_v5.py','nox-control/owner_chat_markdown_acceptance.py','nox-control/owner_workspace_browser_acceptance_v6.py') else {})
    if not set(overrides).issubset(selected):raise RuntimeError('HOLD_SCOPED_BUNDLE_FROZEN_SCOPE')
    found={}
    for path in (*paths,*SCOPED_REPAIR_EXTRA_PATHS.get(entrypoint,()),*overrides.values()):
        name=Path(path).name
        if name not in selected or name in overrides and path!=overrides[name]:continue
        if name in found:raise RuntimeError('HOLD_SCOPED_BUNDLE_DUPLICATE_SOURCE')
        found[name]=path
    if set(found)!=set(selected):raise RuntimeError('HOLD_SCOPED_BUNDLE_MISSING_SOURCE')
    result=tuple(found[name] for name in selected)
    if any(not Path(path).is_file() for path in result):raise RuntimeError('HOLD_SCOPED_BUNDLE_MISSING_FILE')
    return result


SOURCE_EXPORT_META='NOX_MAINT_SOURCE_EXPORT_META='
SOURCE_EXPORT_CHUNK='NOX_MAINT_SOURCE_EXPORT_CHUNK='
SOURCE_EXPORT_COMPLETE='NOX_MAINT_SOURCE_EXPORT_COMPLETE=true'
SOURCE_EXPORT_RECEIPT='NOX_MAINT_SOURCE_EXPORT_RECEIPT='
SOURCE_EXPORT_SCHEMA='NOX_ENCRYPTED_SOURCE_EXPORT_ENVELOPE_V1'
SOURCE_EXPORT_DEPENDENCY_MANIFEST='nox-control/owner_chat_s03_source_export_manifest.json'
SOURCE_EXPORT_DEPENDENCY_MANIFEST_SHA256='abbd044237816411ecdbc81e7887099a3937caeb445504afe606887e22d34eb2'
SOURCE_EXPORT_SUPPORT_PATHS=frozenset(('nox_runpod/__init__.py','nox_runpod/teacher_mesh/__init__.py',
    'nox_runpod/teacher_mesh/v51/__init__.py','nox_runpod/teacher_mesh/v51/ephemeral_ssh_probe.py'))
SOURCE_EXPORT_MAX_BYTES=1024*1024
SOURCE_EXPORT_MAX_CHUNKS=120


def verify_source_export_dependencies():
    """Pin the local, read-only SSH provider needed by the source-export action."""
    manifest_path=Path(SOURCE_EXPORT_DEPENDENCY_MANIFEST)
    try:
        manifest_raw=manifest_path.read_bytes()
    except OSError:
        raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_MANIFEST_MISSING')
    if hashlib.sha256(manifest_raw).hexdigest()!=SOURCE_EXPORT_DEPENDENCY_MANIFEST_SHA256:
        raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_MANIFEST_HASH')
    try:
        manifest=json.loads(manifest_raw)
        canonical=json.dumps(manifest,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    except Exception:
        raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_MANIFEST_JSON')
    if (canonical!=manifest_raw or not isinstance(manifest,dict)
            or set(manifest)!={'schema','files'}
            or manifest.get('schema')!='NOX_S03_EXPORT_RUNTIME_MANIFEST_V1'
            or not isinstance(manifest.get('files'),list) or len(manifest['files'])!=len(SOURCE_EXPORT_SUPPORT_PATHS)):
        raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_MANIFEST_SCHEMA')
    seen=set()
    for record in manifest['files']:
        if not isinstance(record,dict) or set(record)!={'path','sha256'}:
            raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_RECORD')
        path=record.get('path');expected=record.get('sha256')
        if (path not in SOURCE_EXPORT_SUPPORT_PATHS or path in seen
                or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)):
            raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_SCOPE')
        seen.add(path)
        candidate=Path(path)
        try:
            info=candidate.lstat()
            if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                    or info.st_nlink!=1 or info.st_size>32768 or info.st_mode&0o022):
                raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_FILE_UNSAFE')
            raw=candidate.read_bytes()
        except RuntimeError:
            raise
        except OSError:
            raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_FILE_MISSING')
        if hashlib.sha256(raw).hexdigest()!=expected:
            raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_FILE_HASH')
    if seen!=SOURCE_EXPORT_SUPPORT_PATHS:
        raise RuntimeError('HOLD_SOURCE_EXPORT_DEPENDENCY_FILE_MISSING')
    return True

def source_export_key_info(encoded,now=None):
    if not isinstance(encoded,str) or len(encoded)>12000 or not re.fullmatch('[A-Za-z0-9_-]+',encoded):
        raise RuntimeError('HOLD_SOURCE_EXPORT_KEY_FORMAT')
    try:
        raw=base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4))
        value=json.loads(raw)
        canonical=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
        fields={'schema','scope','key_id','transfer_id','created_at','expires_at','public_key_pem'}
        if raw!=canonical or not isinstance(value,dict) or set(value)!=fields:raise ValueError()
        if value.get('schema')!='NOX_OWNER_SOURCE_EXPORT_KEY_V1' or value.get('scope')!='NOX_S03_SOURCE_EXPORT_V1':raise ValueError()
        if not re.fullmatch('[A-Za-z0-9_.-]{1,80}',value.get('key_id','')):raise ValueError()
        if not re.fullmatch('[a-f0-9]{32}',value.get('transfer_id','')):raise ValueError()
        if type(value.get('created_at')) is not int or type(value.get('expires_at')) is not int:raise ValueError()
        now=int(time.time()) if now is None else now
        if value['created_at']>now+300 or value['expires_at']<now or value['expires_at']-value['created_at']>3600:raise ValueError()
        pem=value.get('public_key_pem')
        if not isinstance(pem,str) or len(pem)>12000 or not pem.startswith('-----BEGIN PUBLIC KEY-----\n') or not pem.rstrip().endswith('-----END PUBLIC KEY-----') or 'PRIVATE KEY' in pem:raise ValueError()
        return value
    except Exception:raise RuntimeError('HOLD_SOURCE_EXPORT_KEY_INVALID') from None

def collect_source_export_stdout(stdout,request_id,source_sha):
    lines=stdout.splitlines();meta=None;chunks={};complete=[]
    for line in lines:
        if not line:continue
        if line.startswith('NOX_MAINT_SOURCE_EXPORT_RESULT='):
            code=line.split('=',1)[1]
            raise RuntimeError(code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else 'HOLD_SOURCE_EXPORT_REMOTE')
        if line.startswith(SOURCE_EXPORT_META):
            if meta is not None:raise RuntimeError('HOLD_SOURCE_EXPORT_DUPLICATE_META')
            try:meta=json.loads(line[len(SOURCE_EXPORT_META):])
            except Exception:raise RuntimeError('HOLD_SOURCE_EXPORT_META_JSON') from None
            continue
        if line.startswith(SOURCE_EXPORT_CHUNK):
            try:value=json.loads(line[len(SOURCE_EXPORT_CHUNK):])
            except Exception:raise RuntimeError('HOLD_SOURCE_EXPORT_CHUNK_JSON') from None
            if not isinstance(value,dict) or set(value)!={'transfer_id','index','data_b64'}:raise RuntimeError('HOLD_SOURCE_EXPORT_CHUNK_SCHEMA')
            index=value['index'];chunk=value['data_b64']
            if type(index) is not int or index<0 or index>=SOURCE_EXPORT_MAX_CHUNKS or not isinstance(chunk,str) or len(chunk)>12000 or not re.fullmatch('[A-Za-z0-9+/]*={0,2}',chunk):raise RuntimeError('HOLD_SOURCE_EXPORT_CHUNK_BOUNDS')
            if index in chunks:raise RuntimeError('HOLD_SOURCE_EXPORT_DUPLICATE_CHUNK')
            try:data=base64.b64decode(chunk,validate=True)
            except Exception:raise RuntimeError('HOLD_SOURCE_EXPORT_CHUNK_BASE64') from None
            if len(data)>9000:raise RuntimeError('HOLD_SOURCE_EXPORT_CHUNK_BOUNDS')
            chunks[index]=(value['transfer_id'],data)
            continue
        if line==SOURCE_EXPORT_COMPLETE:
            complete.append(line);continue
        if line.startswith('NOX_MAINT_'):
            raise RuntimeError('HOLD_SOURCE_EXPORT_UNKNOWN_MARKER')
        raise RuntimeError('HOLD_SOURCE_EXPORT_UNEXPECTED_STDOUT')
    if meta is None or len(complete)!=1 or not _has_exact_terminal_completion_marker(stdout,SOURCE_EXPORT_COMPLETE):
        raise RuntimeError('HOLD_SOURCE_EXPORT_INCOMPLETE')
    fields={'schema','request_id','source_sha','transfer_id','key_id','total_bytes','total_chunks','envelope_sha256'}
    if not isinstance(meta,dict) or set(meta)!=fields or meta.get('schema')!='NOX_SOURCE_EXPORT_TRANSFER_V1':raise RuntimeError('HOLD_SOURCE_EXPORT_META_SCHEMA')
    if type(meta.get('request_id')) is not int or meta['request_id']!=int(request_id) or meta.get('source_sha')!=source_sha:raise RuntimeError('HOLD_SOURCE_EXPORT_REQUEST_BINDING')
    if not re.fullmatch('[a-f0-9]{32}',str(meta.get('transfer_id',''))) or not re.fullmatch('[A-Za-z0-9_.-]{1,80}',str(meta.get('key_id',''))):raise RuntimeError('HOLD_SOURCE_EXPORT_META_ID')
    if type(meta.get('total_bytes')) is not int or not 1<=meta['total_bytes']<=SOURCE_EXPORT_MAX_BYTES:raise RuntimeError('HOLD_SOURCE_EXPORT_SIZE')
    if type(meta.get('total_chunks')) is not int or not 1<=meta['total_chunks']<=SOURCE_EXPORT_MAX_CHUNKS or len(chunks)!=meta['total_chunks']:raise RuntimeError('HOLD_SOURCE_EXPORT_CHUNK_COUNT')
    if set(chunks)!=set(range(meta['total_chunks'])):raise RuntimeError('HOLD_SOURCE_EXPORT_CHUNK_ORDER')
    parts=[]
    for index in range(meta['total_chunks']):
        tid,data=chunks[index]
        if tid!=meta['transfer_id']:raise RuntimeError('HOLD_SOURCE_EXPORT_CHUNK_BINDING')
        parts.append(data)
    envelope=b''.join(parts)
    if len(envelope)!=meta['total_bytes'] or hashlib.sha256(envelope).hexdigest()!=meta['envelope_sha256']:raise RuntimeError('HOLD_SOURCE_EXPORT_ENVELOPE_HASH')
    try:value=json.loads(envelope)
    except Exception:raise RuntimeError('HOLD_SOURCE_EXPORT_ENVELOPE_JSON') from None
    required={'schema','request_id','source_sha','transfer_id','key_id','bundle_sha256','aad_b64','wrapped_key_b64','nonce_b64','ciphertext_b64'}
    if not isinstance(value,dict) or set(value)!=required or value.get('schema')!=SOURCE_EXPORT_SCHEMA:raise RuntimeError('HOLD_SOURCE_EXPORT_ENVELOPE_SCHEMA')
    for key in ('request_id','source_sha','transfer_id','key_id'):
        if value.get(key)!=meta.get(key):raise RuntimeError('HOLD_SOURCE_EXPORT_ENVELOPE_BINDING')
    if not re.fullmatch('[0-9a-f]{64}',str(value.get('bundle_sha256',''))):raise RuntimeError('HOLD_SOURCE_EXPORT_BUNDLE_HASH')
    try:
        aad=base64.b64decode(value['aad_b64'],validate=True)
        wrapped=base64.b64decode(value['wrapped_key_b64'],validate=True)
        nonce=base64.b64decode(value['nonce_b64'],validate=True)
        cipher=base64.b64decode(value['ciphertext_b64'],validate=True)
        aad_value=json.loads(aad)
    except Exception:raise RuntimeError('HOLD_SOURCE_EXPORT_ENVELOPE_ENCODING') from None
    expected_aad={'schema':'NOX_S03_SOURCE_EXPORT_V1','request_id':request_id,'source_sha':source_sha,'transfer_id':meta['transfer_id'],'key_id':meta['key_id'],'bundle_sha256':value['bundle_sha256']}
    if aad!=json.dumps(expected_aad,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode() or aad_value!=expected_aad:raise RuntimeError('HOLD_SOURCE_EXPORT_AAD_BINDING')
    if len(wrapped)!=512 or len(nonce)!=12 or not 16<=len(cipher)<=SOURCE_EXPORT_MAX_BYTES:raise RuntimeError('HOLD_SOURCE_EXPORT_CRYPTO_BOUNDS')
    canonical=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
    if canonical!=envelope:raise RuntimeError('HOLD_SOURCE_EXPORT_ENVELOPE_CANONICAL')
    return meta,envelope

def write_source_export_artifact(envelope):
    directory=Path('artifacts')
    try:directory.mkdir(mode=0o700)
    except FileExistsError:pass
    st=directory.lstat()
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_mode&0o022:raise RuntimeError('HOLD_SOURCE_EXPORT_ARTIFACT_DIR')
    path=directory/'nox-s03-source-export.enc'
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        view=memoryview(envelope);offset=0
        while offset<len(view):offset+=os.write(fd,view[offset:])
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        with contextlib.suppress(OSError):path.unlink()
        raise
    else:os.close(fd)


def authorize_event(action,export_key_b64=None):
    if action not in FILES:raise RuntimeError('HOLD_ACTION_NOT_ALLOWLISTED')
    e=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_EVENT_NAME')!='issue_comment':raise RuntimeError('HOLD_EVENT_SCOPE')
    c=e.get('comment',{});owner=e.get('repository',{}).get('owner',{})
    if (c.get('user',{}).get('id')!=OWNER_ID or owner.get('id')!=OWNER_ID or c.get('author_association')!='OWNER'
            or e.get('issue',{}).get('number')!=256 or e.get('sender',{}).get('id')!=OWNER_ID):raise RuntimeError('HOLD_OWNER_COMMAND_IDENTITY')
    sha=os.environ.get('NOX_PINNED_SOURCE_SHA','')
    if not re.fullmatch('[0-9a-f]{40}',sha):raise RuntimeError('HOLD_SOURCE_PIN')
    expected=f'/nox-maintain {INSTANCE} {sha} {action}'
    if action=='source_export':
        source_export_key_info(export_key_b64)
        expected+=' '+export_key_b64
    elif export_key_b64 is not None:raise RuntimeError('HOLD_UNEXPECTED_EXPORT_KEY')
    if c.get('body')!=expected:raise RuntimeError('HOLD_EXACT_OWNER_COMMAND')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise RuntimeError('HOLD_CHECKOUT_MISMATCH')
    return c['id']

def run_native(action,request_id,export_key_b64=None,provider_cleanup_sink=None):
    if action not in FILES:raise RuntimeError('HOLD_ACTION_NOT_ALLOWLISTED')
    if action=='source_export':source_export_key_info(export_key_b64)
    elif export_key_b64 is not None:raise RuntimeError('HOLD_UNEXPECTED_EXPORT_KEY')
    global MASTER
    provider_root=Path(__file__).resolve().parents[1]
    verify_source_export_dependencies()
    provider_root_text=str(provider_root)
    if provider_root_text not in sys.path:sys.path.insert(0,provider_root_text)
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
    expected_provider=(provider_root/'nox_runpod'/'teacher_mesh'/'v51'/'ephemeral_ssh_probe.py').resolve()
    imported_provider=Path(getattr(s,'__file__','')).resolve()
    if imported_provider!=expected_provider:raise RuntimeError('HOLD_SOURCE_EXPORT_PROVIDER_IMPORT_PATH')
    if provider_cleanup_sink is not None:
        if not callable(provider_cleanup_sink):raise RuntimeError('HOLD_SOURCE_EXPORT_PROVIDER_CLEANUP_SINK')
        provider_cleanup_sink(s.cleanup)
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
    # Classify SSH failures without printing stderr, user names, IPs, keys,
    # file paths or host fingerprints. Used only for owner diagnostics.
    # Distinguish wrong key propagation from a down socket or mux failure.
    def ssh_failure_class(stderr):
        if not isinstance(stderr, str):
            return 'UNKNOWN'
        message = stderr[:2048].lower()
        rules = (
            ('authentication refused: bad ownership or modes', 'BAD_AUTHORIZED_KEYS_PERMISSIONS'),
            ('permission denied (publickey)', 'PUBLICKEY_REJECTED'),
            ('too many authentication failures', 'TOO_MANY_AUTH_FAILURES'),
            ('host key verification failed', 'HOST_KEY_REJECTED'),
            ('remote host identification has changed', 'HOST_KEY_REJECTED'),
            ('connection reset by', 'CONNECTION_RESET'),
            ('connection closed by', 'CONNECTION_CLOSED'),
            ('connection refused', 'CONNECTION_REFUSED'),
            ('connection timed out', 'CONNECTION_TIMEOUT'),
            ('operation timed out', 'CONNECTION_TIMEOUT'),
            ('no route to host', 'ROUTE_UNAVAILABLE'),
            ('network is unreachable', 'ROUTE_UNAVAILABLE'),
            ('controlpath', 'MUX_SOCKET_FAILURE'),
            ('mux_client', 'MUX_SOCKET_FAILURE'),
            ('kex_exchange_identification', 'KEX_FAILURE'),
            ('banner exchange', 'KEX_FAILURE'),
        )
        return next((code for token, code in rules if token in message), 'UNKNOWN')
    # Authenticate the persistent connection, not a disposable 'true' session.
    # Retry only before any payload has been sent.
    for attempt in range(8):
        try:
            r=subprocess.run(common+['-o','ControlMaster=yes','-o','ControlPersist=90','-N','-f',host],capture_output=True,text=True,timeout=25)
        except subprocess.TimeoutExpired:r=None
        if r is not None and r.returncode==0 and sock.exists():
            MASTER=common+['-O','exit',host]
            break
        reason = 'PROCESS_TIMEOUT' if r is None else ssh_failure_class(r.stderr)
        print('NOX_MAINT_AUTH_ATTEMPT='+str(attempt+1)+'_RETRY',flush=True)
        print('NOX_MAINT_SSH_FAILURE_CLASS='+reason,flush=True)
        time.sleep(5)
    else:raise RuntimeError('HOLD_SSH_AUTHENTICATION')
    check=subprocess.run(common+['-O','check',host],capture_output=True,text=True,timeout=8)
    if check.returncode:raise RuntimeError('HOLD_SSH_MASTER_NOT_ALIVE')
    print('NOX_MAINT_AUTHENTICATED_INSTANCE=60509551',flush=True)
    payload=Path(FILES[action]).read_text()
    if action == 'lifeline':
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
    elif action in ('stage','repair','reflex_successor'):
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
    export_env=(f'NOX_OWNER_EXPORT_KEY_B64={shlex.quote(export_key_b64)} ' if action=='source_export' else '')
    script=f"set -euo pipefail\n{export_env}NOX_OWNER_SOURCE_SHA={sha} NOX_OWNER_REQUEST_ID={int(request_id)} python3 - <<'NOX_OWNER_PAYLOAD\n"+payload+"\nNOX_OWNER_PAYLOAD\n"
    timeout=150 if action in ('audit','inspect','source_attest','source_export') else 900
    # Reuse the authenticated channel. A dead master must not fall back to
    # a fresh, potentially ambiguous TCP connection while starting a mutation.
    r=subprocess.run(common+['-o','ControlMaster=no','-o','ProxyCommand=false',host,'bash','-se'],input=script,capture_output=True,text=True,timeout=timeout)
    source_sha=os.environ.get('NOX_PINNED_SOURCE_SHA','')
    if action=='source_export':
        export_meta,envelope=collect_source_export_stdout(r.stdout,int(request_id),source_sha)
        write_source_export_artifact(envelope)
        forwarded=[SOURCE_EXPORT_RECEIPT+json.dumps(export_meta,sort_keys=True,separators=(',',':')),SOURCE_EXPORT_COMPLETE]
    else:forwarded=forward_remote_stdout(r.stdout,action,int(request_id),source_sha)
    for line in forwarded:print(line,flush=True)
    print('NOX_MAINT_REMOTE_EXIT_CODE='+str(r.returncode),flush=True)
    if r.returncode:
        err=r.stderr.lower()
        cls='AUTH' if 'permission denied' in err else 'TIMEOUT' if 'timed out' in err else 'CONNECTION' if 'connect' in err else 'PAYLOAD'
        print('NOX_MAINT_FAILURE_CLASS='+cls,flush=True)
    marker=SOURCE_ATTEST_COMPLETE_TRUE if action=='source_attest' else SOURCE_EXPORT_COMPLETE if action=='source_export' else 'NOX_MAINT_'+action.upper()+'_COMPLETE=true'
    if r.returncode or not _has_exact_terminal_completion_marker(r.stdout,marker):
        hold='HOLD_SOURCE_ATTESTATION_INCOMPLETE' if action=='source_attest' else 'HOLD_NATIVE_PAYLOAD_INCOMPLETE'
        raise RuntimeError(hold)
    if action=='audit':
        gate=audit_census_status(r.stdout)
        print('NOX_MAINT_AUDIT_CENSUS_GATE='+json.dumps(gate,separators=(',',':'),sort_keys=True),flush=True)
        require_audit_census_complete(r.stdout)
    return True

def operator_argument_parser():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=FILES);parser.add_argument('export_key',nargs='?');return parser

def main():
    args=operator_argument_parser().parse_args();good=False
    verified_provider_cleanup=None
    def capture_verified_provider_cleanup(cleanup):
        nonlocal verified_provider_cleanup
        if not callable(cleanup):raise RuntimeError('HOLD_SOURCE_EXPORT_PROVIDER_CLEANUP_MISSING')
        verified_provider_cleanup=cleanup
    try:
        request=authorize_event(args.action,args.export_key)
        print('NOX_MAINT_AUTHORIZED_COMMENT_ID='+str(request),flush=True)
        good=run_native(args.action,request,args.export_key,capture_verified_provider_cleanup)
    except Exception as e:
        code=str(e)
        print('NOX_MAINT_RESULT='+(code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else 'HOLD_'+type(e).__name__.upper()),flush=True)
    finally:
        if MASTER:
            with contextlib.suppress(Exception):subprocess.run(MASTER,capture_output=True,timeout=8)
        if verified_provider_cleanup is not None:
            try:
                if not verified_provider_cleanup():good=False
            except Exception:print('NOX_MAINT_CLEANUP=HOLD');good=False
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
