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
FILES={'audit': 'nox-control/owner_native_audit.py', 'inspect': 'nox-control/owner_native_inspect.py', 'stage': 'nox-control/owner_native_stage.py', 'repair': 'nox-control/systemic_relay_20261118/owner_native_reflex_restore_entry.py', 'lifeline': 'nox-control/owner_native_lifeline.py'}
MASTER=None

# GitHub Actions may omit an individual log line above the operator's historical
# 180k character threshold. Preserve oversized evidence as small, independently
# verifiable records so consumers can detect missing, reordered, or corrupt data.
MAX_FORWARD_LINE_BYTES=160000
TRANSFER_CHUNK_BYTES=16384
TRANSFER_MAX_BYTES=8*1024*1024
TRANSFER_PREFIX='NOX_MAINT_TRANSFER_'
AUDIT_PREFIX='NOX_MAINT_AUDIT='
AUDIT_COMPLETE='NOX_MAINT_AUDIT_COMPLETE=true'
AUDIT_SECTIONS=('hardware','process_rows','supervisor','packages','models','storage','mount_inventory')
TRANSFER_MARKER_RE=re.compile(r'^(NOX_MAINT_[A-Z0-9_]+)=')

def _transfer_record(kind,value):
    return TRANSFER_PREFIX+kind+'='+json.dumps(value,separators=(',',':'),sort_keys=True)

def build_transfer_records(marker_line,request_id,source_sha,force=False):
    """Encode one NOX marker into a bounded BEGIN/CHUNK*/END transfer."""
    match=TRANSFER_MARKER_RE.match(marker_line)
    if not match:raise RuntimeError('HOLD_TRANSFER_MARKER_FORMAT')
    if type(request_id) is not int or request_id<1:raise RuntimeError('HOLD_TRANSFER_REQUEST_ID')
    if not re.fullmatch(r'[0-9a-f]{40}',str(source_sha)):raise RuntimeError('HOLD_TRANSFER_SOURCE_SHA')
    raw=marker_line.encode('utf-8')
    if len(raw)>TRANSFER_MAX_BYTES:raise RuntimeError('HOLD_TRANSFER_ARTIFACT_OVERSIZE')
    if not force and len(raw)<MAX_FORWARD_LINE_BYTES:return [marker_line]
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
    if any(len(line.encode('utf-8'))>=MAX_FORWARD_LINE_BYTES for line in records):
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
        if not isinstance(line,str) or len(line.encode('utf-8'))>=MAX_FORWARD_LINE_BYTES:
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

def audit_bundle_line(stdout):
    """Require the complete, unique seven-worker audit before it is forwarded."""
    rows=[];complete=[];sections=[];row_positions=[];complete_positions=[]
    for position,line in enumerate(stdout.splitlines()):
        if line==AUDIT_COMPLETE:
            complete.append(line);complete_positions.append(position)
        if line.startswith(AUDIT_PREFIX):
            try:row=json.loads(line[len(AUDIT_PREFIX):])
            except (ValueError,TypeError) as exc:raise RuntimeError('HOLD_AUDIT_ROW_INVALID') from exc
            if not isinstance(row,dict) or row.get('section') not in AUDIT_SECTIONS:
                raise RuntimeError('HOLD_AUDIT_SECTION_INVALID')
            if 'error' in row or not isinstance(row.get('result'),dict):
                raise RuntimeError('HOLD_AUDIT_WORKER_INCOMPLETE')
            if type(row.get('worker_pid')) is not int or row['worker_pid']<1:
                raise RuntimeError('HOLD_AUDIT_WORKER_IDENTITY')
            if row['section']=='process_rows':
                inventory=row.get('bounded_process_identity_inventory')
                if not isinstance(inventory,dict):raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_MISSING')
                process_rows=inventory.get('rows')
                expected_fields=['pid','ppid','uid','start_ticks','nspid','namespaces.pid',
                    'namespaces.mnt','namespaces.cgroup','comm','exe','exe_state']
                expected_omitted=['argv','cmdline','environ','cgroup_paths']
                if (not isinstance(process_rows,list) or type(inventory.get('complete')) is not bool
                        or type(inventory.get('truncated')) is not bool
                        or inventory.get('scope')!='ALL_NUMERIC_PROC_PIDS_MINIMAL_IDENTITY'
                        or type(inventory.get('row_count')) is not int
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
                        or inventory.get('fields')!=expected_fields
                        or inventory.get('omitted_fields')!=expected_omitted
                        or 'enumeration_error' not in inventory
                        or (inventory['enumeration_error'] is not None
                            and not re.fullmatch(r'[A-Za-z0-9_]{1,64}',str(inventory['enumeration_error'])))
                        or any(not isinstance(item,dict) or type(item.get('pid')) is not int or item['pid']<1
                               or not {'pid','ppid','uid','start_ticks','nspid','namespaces','comm','exe','exe_state','identity_state'}.issubset(item)
                               for item in process_rows)
                        or not re.fullmatch(r'[0-9a-f]{64}',str(inventory.get('rows_sha256')))):
                    raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_SHAPE')
                pids=[item['pid'] for item in process_rows]
                if pids!=sorted(set(pids)):
                    raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_PID_ORDER')
                row_digest=hashlib.sha256(json.dumps(process_rows,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
                if row_digest!=inventory['rows_sha256']:
                    raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_SHA')
                if inventory['complete']:
                    if (inventory['truncated'] or inventory['enumeration_error'] is not None
                            or inventory['read_failure_count']!=0 or inventory['read_failure_pids']
                            or inventory['entries_seen']!=inventory['row_count']
                            or any(item['identity_state']!='VERIFIED' for item in process_rows)):
                        raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_CONTRADICTION')
                    for item in process_rows:
                        namespaces=item['namespaces'];nspid=item['nspid']
                        if (type(item['ppid']) is not int or item['ppid']<0
                                or type(item['uid']) is not int or item['uid']<0
                                or type(item['start_ticks']) is not int or item['start_ticks']<=0
                                or not isinstance(nspid,list) or not nspid or len(nspid)>16
                                or any(type(pid) is not int or pid<1 for pid in nspid)
                                or not isinstance(namespaces,dict)
                                or any(not isinstance(namespaces.get(ns),str)
                                       or not re.fullmatch(rf'{ns}:\[[0-9]+\]',namespaces[ns])
                                       for ns in ('pid','mnt','cgroup'))
                                or not isinstance(item['comm'],str) or not item['comm']
                                or item['exe_state'] not in ('AVAILABLE','MISSING')
                                or (item['exe_state']=='AVAILABLE' and not isinstance(item['exe'],str))
                                or (item['exe_state']=='MISSING' and item['exe'] is not None)):
                            raise RuntimeError('HOLD_AUDIT_PROCESS_INVENTORY_IDENTITY')
            rows.append((line,row['section']))
            sections.append(row['section']);row_positions.append(position)
    if (len(complete)!=1 or len(rows)!=len(AUDIT_SECTIONS) or sections!=list(AUDIT_SECTIONS)
            or complete_positions[0]<max(row_positions)):
        raise RuntimeError('HOLD_AUDIT_RECORD_SET_INCOMPLETE')
    bundle='NOX_MAINT_AUDIT_BUNDLE='+'\n'.join(line for line,_ in rows)
    return bundle

def audit_census_status(stdout):
    """Return the independent acceptance gates carried by the full audit rows."""
    bundle=audit_bundle_line(stdout)
    rows=[json.loads(line[len(AUDIT_PREFIX):])
          for line in bundle.split('=',1)[1].splitlines()]
    by_section={row['section']:row for row in rows}
    process=by_section['process_rows']['bounded_process_identity_inventory']
    process_complete=(process['complete'] is True and not process['truncated']
        and process['enumeration_error'] is None and process['read_failure_count']==0
        and process['entries_seen']==process['row_count']==len(process['rows'])
        and process['row_count']<=process['cap'])

    hardware=by_section['hardware']['result']
    services=hardware.get('supervisor_services')
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

    before=hardware.get('gpu_apps_before');after=hardware.get('gpu_apps_after')
    links=hardware.get('gpu_process_links')
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
            for app in apps if isinstance(app,dict)) and all(isinstance(app,dict) for app in apps)
        keys=[(app['gpu_pid'],app['gpu_uuid']) for app in apps] if valid else []
        return valid and len(keys)==len(set(keys))
    expected_links=set()
    if gpu_inventory_valid(before) and gpu_inventory_valid(after):
        expected_links={(app['gpu_pid'],app['gpu_uuid']) for app in before['apps']+after['apps']}
    observed_links=set();links_valid=isinstance(links,list)
    if links_valid:
        allowed={'MATCHED','NAMESPACE_ALIAS','NO_SERVICE_ANCESTOR'}
        for link in links:
            if not isinstance(link,dict):links_valid=False;break
            key=(link.get('gpu_pid'),link.get('gpu_uuid'))
            if (key in observed_links or key not in expected_links
                    or link.get('evidence_state')!='COMPLETE'
                    or link.get('classification') not in allowed
                    or link.get('identity_stability') not in ('STABLE_BOTH','POST_ONLY')):
                links_valid=False;break
            observed_links.add(key)
    gpu_complete=(gpu_inventory_valid(before) and gpu_inventory_valid(after)
        and links_valid and observed_links==expected_links)
    return {'process_census_complete':process_complete,
            'supervisor_inventory_complete':supervisor_complete,
            'supervisor_command_rc':service_rc,
            'supervisor_command_success':services.get('command_success') if isinstance(services,dict) else None,
            'supervisor_service_health':service_health,
            'gpu_census_complete':gpu_complete,
            'process_row_count':process['row_count'],
            'process_rows_sha256':process['rows_sha256'],
            'gpu_link_count':len(links) if isinstance(links,list) else None,
            'gpu_pid_reconciliation':[{'gpu_pid':link.get('gpu_pid'),'gpu_uuid':link.get('gpu_uuid'),
                'classification':link.get('classification'),'evidence_state':link.get('evidence_state'),
                'visibility':link.get('visibility'),'identity_stability':link.get('identity_stability')}
                for link in links if isinstance(link,dict)] if isinstance(links,list) else None}

def require_audit_census_complete(stdout):
    gate=audit_census_status(stdout)
    if not (gate['process_census_complete'] and gate['supervisor_inventory_complete']
            and gate['gpu_census_complete']):
        raise RuntimeError('HOLD_AUDIT_CENSUS_INCOMPLETE')
    return gate

def forward_remote_stdout(stdout,action,request_id,source_sha):
    """Return only bounded marker lines; oversized audit records become a verified bundle."""
    lines=stdout.splitlines();forwarded=[];audit_bundle=None
    if action=='audit':
        audit_bundle=audit_bundle_line(stdout)
        bundle_records=build_transfer_records(audit_bundle,request_id,source_sha,force=True)
        if reassemble_transfer_records(bundle_records,request_id,source_sha)!=audit_bundle.encode('utf-8'):
            raise RuntimeError('HOLD_AUDIT_BUNDLE_REASSEMBLY')
    for line in lines:
        if not line.startswith('NOX_MAINT_'):continue
        if line.startswith(AUDIT_PREFIX):continue
        if action=='audit' and line==AUDIT_COMPLETE:
            forwarded.extend(bundle_records)
            forwarded.append('NOX_MAINT_AUDIT_WORKERS_COMPLETE=true')
            continue
        if len(line.encode('utf-8'))<MAX_FORWARD_LINE_BYTES:
            forwarded.append(line)
            continue
        records=build_transfer_records(line,request_id,source_sha)
        if len(records)==1:
            raise RuntimeError('HOLD_REMOTE_MARKER_NOT_CHUNKED')
        if reassemble_transfer_records(records,request_id,source_sha)!=line.encode('utf-8'):
            raise RuntimeError('HOLD_REMOTE_MARKER_REASSEMBLY')
        forwarded.extend(records)
    if action=='audit' and not any(line=='NOX_MAINT_AUDIT_WORKERS_COMPLETE=true' for line in forwarded):
        raise RuntimeError('HOLD_AUDIT_WORKERS_COMPLETE_MARKER_MISSING')
    return forwarded

SCOPED_REPAIR_BUNDLES={'nox-control/systemic_relay_20261118/owner_chat_policy_live_smoke_entry.py': (), 'nox-control/systemic_relay_20261118/owner_chat_policy_live_smoke.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_counter_reconcile_policy_v1/owner_chat_counter_policy_entry.py': (), 'nox-control/systemic_relay_20261118/next_reviewed_merge_20261118/prepared_v3/owner_systemic_reviewed_merge_embedded_entry.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_v5/owner_chat_decomposition_embedded_entry.py': (), 'nox-control/owner_continuous_executor_install.py': ('cw_test_nox_forge_language_task_coverage.py', 'cw_test_nox_readonly_retry_backoff.py', 'cw_test_nox_warm_cache_limit_contract.py', 'cw_contract_510dbdec4dd2538ebeac.json', 'cw_contract_9efad5217ab0e554a383.json', 'cw_contract_683c5086d66e750d4ed1.json', 'continuous_transaction_helpers.py', 'continuous_dispatcher.py', 'continuous_planner.py', 'continuous_truth.py'), 'nox-control/owner_bounded_cpu_install.py': ('bc_runtime_d5fb476f53e64d2014f2.py', 'bc_runtime_6c67e567e669b993d016.py', 'bc_runtime_2c83ec53f7ee7c2d76bc.py', 'bc_runtime_294473d35d4870f50467.py'), 'nox-control/owner_project_runtime_update.py': ('ru_runtime_fcb77cc59eb9a88dde68.py', 'ru_runtime_84d54c647b0a63447aca.py', 'ru_runtime_52e62a143d16f387899f.py', 'ru_runtime_aa0dd1c8266106b599ce.py', 'ru_plans_a171fa7a94084a1f4b67.data', 'ru_blobs_fa3d69e506d727295094.data', 'ru_plans_79b77425ff05d3337c2e.data', 'ru_blobs_b980a61884965f4838f8.data', 'ru_plans_dd24421576ae4160fa01.data', 'ru_blobs_7e625acddd71fe95988e.data', 'ru_blobs_4b06687bbad8fe6ab046.data', 'ru_contracts_eece310e5608fa9c633d.data'), 'nox-control/owner_complete_executor_install.py': ('ce_runtime_2c4735938dacd2a062ed.py', 'ce_runtime_71dd03dee52f1673c297.py', 'ce_runtime_f6b2f98ac5c7c291ffef.py', 'ce_runtime_687ea3b3548badf9b7ba.py', 'ce_runtime_35b0e94f9c883da017e4.py', 'ce_runtime_d0ff44d4752128c26779.py', 'ce_runtime_119115603be6dba84121.py', 'ce_runtime_7f18d69529582b65f7b8.py', 'ce_runtime_126c77c1281b74676930.py', 'ce_runtime_485d4a4a571c434afb98.py', 'ce_baseline_bb2c543979ad58801d97.source', 'ce_baseline_4d1274059d034bb9b96a.source', 'ce_baseline_d9ec6a8250a167d774ba.source', 'ce_baseline_c676fdda4fa47d316eb1.source', 'ce_baseline_8657ad367e6dd25b48ca.source', 'ce_baseline_006fc038f43682fa36d2.source', 'ce_baseline_d35064a3fc5707dfc174.source', 'ce_baseline_66a6617d6f582876dbdc.source', 'ce_baseline_e3b0c44298fc1c149afb.source', 'ce_baseline_092db7d32a048c1706da.source', 'ce_baseline_dc19594b45a7fae32bf9.source', 'ce_baseline_b4ece67144248808a12c.source', 'ce_baseline_21f8538fec15d39b4dbc.source', 'ce_baseline_3efe025681c3a54cbfac.source', 'ce_baseline_b3c5d26011400b110a1b.source', 'ce_baseline_f299d32099c25ea1822c.source', 'ce_baseline_0fff97b7e758e3e43073.source', 'ce_baseline_fd815f9a743bfcdf6e71.source', 'ce_baseline_97c433b8893514f5812b.source', 'ce_baseline_fc5d6c564c651c2abc81.source', 'ce_baseline_623bfb4ba2d28d3dd3db.source', 'ce_baseline_9201bc3629682a577c80.source', 'ce_baseline_d6042e38549360ace8f9.source', 'ce_baseline_2860173d8d6ed7147af2.source', 'ce_baseline_970d6681ce5dc57156e2.source', 'ce_baseline_6aa9265942695d2b54b3.source', 'ce_baseline_8d2070c2f0819e7d1c2b.source', 'ce_baseline_60e28219f670a8449a56.source', 'ce_plans_283ff826ba1180398888.json', 'ce_blobs_fa3d69e506d727295094.source', 'ce_plans_e7c99335a4a790202f22.json', 'ce_blobs_f7b69405224c63868b76.source', 'ce_plans_de41f4de77a043c695fe.json', 'ce_blobs_7e625acddd71fe95988e.source', 'ce_plans_67e819b4ff1b94cc5bdd.json', 'ce_blobs_b980a61884965f4838f8.source', 'ce_plans_4037501920f2e9f3ea41.json', 'ce_blobs_06940cb13bd568d4cfaa.source', 'ce_plans_9b80e2075b52602ac9e1.json', 'ce_blobs_f336c58fb5062aec6d5b.source', 'ce_contracts_b40696685ca2b7c848a2.json', 'ce_manifests_79a8efb2d344479471bd.json', 'ce_manifests_e040c40bd8ee3d29b0cc.json'), 'nox-control/owner_post_reset_state_observe.py': (), 'nox-control/owner_chat_markdown_asset_install_v2.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'nox-v24-chat-markdown-final.js'), 'nox-control/owner_chat_markdown_metadata.py': (), 'nox-control/owner_chat_markdown_asset_install.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'nox-v24-chat-markdown-final.js'), 'nox-control/owner_workspace_browser_acceptance_v6.py': ('owner_workspace_browser_acceptance_v5.py', 'owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_checkpoint_proof_v2.py': (), 'nox-control/owner_workspace_browser_acceptance_v5.py': ('owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_chat_markdown_acceptance.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_memfd_progress.py': (), 'nox-control/owner_qwen_successor_checkpoint_proof.py': (), 'nox-control/owner_qwen_successor_observe_v2.py': (), 'nox-control/owner_workspace_browser_acceptance_v3.py': ('owner_workspace_browser_acceptance_v2.py', 'owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_entry_v2.py': ('owner_qwen_successor_install_v2.py', 'owner_qwen_execution_successor.py', 'qwen_student_training_entry_successor.py', 'owner_qwen_successor_guard.py', 'owner_qwen_successor_status.py', 'owner_qwen_successor_media_handoff.py', 'owner_qwen_successor_media_guard.py', 'owner_qwen_successor_handback_retry.py', 'owner_qwen_successor_hermes_hydrate.py', 'owner_qwen_successor_watch.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_workspace_browser_acceptance_v2.py': ('owner_workspace_browser_acceptance.py', 'owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_successor_entry.py': ('owner_qwen_successor_install.py', 'owner_qwen_execution_successor.py', 'qwen_student_training_entry_successor.py', 'owner_qwen_successor_guard.py', 'owner_qwen_successor_status.py', 'owner_qwen_successor_media_handoff.py', 'owner_qwen_successor_media_guard.py', 'owner_qwen_successor_handback_retry.py', 'owner_qwen_successor_hermes_hydrate.py', 'owner_qwen_successor_watch.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_workspace_browser_acceptance.py': ('owner_chat_page_diagnose.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_qwen_budget_failure_diagnose.py': (), 'nox-control/owner_workspace_asset_install.py': ('owner_chat_stream_asset_install_v2.py', 'owner_media_acceptance_entry.py', 'owner_native_repair.py', 'workspace-owner-capabilities.js'), 'nox-control/owner_qwen_public_memfd_access_probe.py': (), 'nox-control/owner_training_control_readonly_batch.py': ('owner_qwen_transport_budget_observe.py', 'owner_admin_control_structure_probe.py', 'owner_qwen_public_memfd_access_probe.py'), 'nox-control/owner_qwen_transport_budget_observe.py': (), 'nox-control/owner_admin_control_structure_probe.py': (), 'nox-control/owner_qwen_transport_budget_finalize_6914959637.py': (), 'nox-control/owner_chat_page_diagnose.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py'), 'nox-control/owner_chat_action_routing_install.py': ('owner_chat_stream_action_routing.py', 'owner_download_status_entry.py', 'owner_native_repair.py'), 'nox-control/owner_chat_plan_api_probe.py': (), 'nox-control/owner_chat_stream_asset_install_v2.py': ('nox-v135-resonance-owner-bridge-coalesced.js', 'owner_media_acceptance_entry.py', 'owner_native_repair.py'), 'nox-control/owner_qwen_transport_rollback_entry.py': ('owner_qwen_transport_rollback.py', 'owner_qwen_transport_revision_install.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py', 'owner_qwen_transport_failed_diagnostic.json'), 'nox-control/owner_qwen_transport_budget_entry.py': ('owner_qwen_revision_install.py', 'qwen_student_training_entry_revision.py', 'owner_qwen_transport_budget_install.py', 'qwen_student_training_entry_transport_budget.py', 'owner_qwen_execution_revision.py', 'owner_qwen_revision_guard.py', 'owner_qwen_revision_status.py', 'owner_qwen_revision_media_handoff.py', 'owner_qwen_revision_media_guard.py', 'owner_qwen_revision_handback_retry.py', 'owner_hermes_revision_hydrate.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_chat_stream_asset_install.py': ('nox-v135-resonance-owner-bridge-coalesced.js', 'owner_media_acceptance_entry.py', 'owner_native_repair.py'), 'nox-control/owner_browser_asset_identity_entry.py': ('owner_browser_normal_motion_entry.py', 'owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py', 'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py', 'owner_chat_normal_motion_qa.py', 'owner_chat_asset_identity_qa.py'), 'nox-control/owner_qwen_held_media_smoke_v2_entry.py': ('owner_qwen_held_media_smoke_v2.py', 'owner_media_acceptance_entry.py', 'owner_qwen_revision_install.py', 'owner_native_repair.py', 'owner_download_status_entry.py'), 'nox-control/owner_browser_normal_motion_entry.py': ('owner_browser_stream_only_entry.py', 'owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py', 'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py', 'owner_chat_normal_motion_qa.py'), 'nox-control/owner_qwen_held_media_smoke_entry.py': ('owner_qwen_held_media_smoke.py', 'owner_media_acceptance_entry.py', 'owner_qwen_revision_install.py', 'owner_native_repair.py', 'owner_download_status_entry.py'), 'nox-control/owner_qwen_transport_install_entry.py': ('owner_qwen_revision_install.py', 'qwen_student_training_entry_revision.py', 'owner_qwen_transport_revision_install.py', 'qwen_student_training_entry_transport_candidate.py', 'owner_qwen_execution_revision.py', 'owner_qwen_revision_guard.py', 'owner_qwen_revision_status.py', 'owner_qwen_revision_media_handoff.py', 'owner_qwen_revision_media_guard.py', 'owner_qwen_revision_handback_retry.py', 'owner_hermes_revision_hydrate.py', 'owner_download_status_entry.py', 'owner_native_repair.py', 'owner_qwen_disk_rearm_entry.py'), 'nox-control/owner_reviewed_rescue_catalog_append.py': ('rv_plan_379d1c5b50e42fb50165ce1fbe904cf47b1b45b3747878c60f9b1208d6e13e23.json', 'rv_payload_5201af0115e1ead68d3369794e33bbc97d7b7b2f00762c5c2ecfdaa7dda45926.source', 'rv_payload_4329f7389b24cfbb1fbb47c91b43eb7407bf18c95d15064fc7ea8166cde0a821.source'), 'nox-control/owner_kernel_self_fd_install.py': ('sf_runtime_192d0c1b7b87447d4f08.py', 'sf_plan_457dbaf4484cfb5b7e14.json', 'sf_payload_5201af0115e1ead68d33.source', 'sf_payload_4329f7389b24cfbb1fbb.source', 'sf_fd_descriptor_768d28516014a124a380.json'), 'nox-control/owner_reviewed_proc_followup_catalog_append.py': ('fu_plan_3f620116ee563127d7e94bfeac7aae1408aaa4f1752f431fee774c49023e6509.json', 'fu_payload_a71051c085f8bfdbeda93f3f4c16501444ca35942ac4ca7f3a46d7bd16acfbbc.source', 'fu_payload_f5c8eb6b42e71efa38745bc6f729a989b4a199999d7c3b9aa45cebbde36f851a.source'), 'nox-control/owner_model_slot_recovery.py': ('slot_contract_3f43e152774c159bbe45.json', 'slot_contract_60a6abf6691f6c3fb186.json', 'slot_transaction_helpers.py', 'slot_model_client.py'), 'nox-control/owner_c02_memory_progress_install.py': ('c02_contract_4a8f20c371f3211c2351.json', 'c02_test_nox_c02_existing_cognition.py', 'c02_test_nox_c02_optional_starvation.py', 'c02_transaction_helpers.py'), 'nox-control/owner_c02_memory_reviewed_recovery.py': ('c02r_payload_b504248ac1ae4a093382.source', 'c02r_plan_5d05ba50d058981ce8ba.json', 'c02r_transaction_helpers.py'), 'nox-control/systemic_relay_20261118/owner_systemic_relay_entry.py': ('systemic_owner_subagent_dispatcher.py', 'systemic_owner_subagent_processes.py', 'systemic_owner_project_native.py', 'systemic_owner_project_planner.py', 'systemic_owner_subagent_instruction_truth.py', 'systemic_owner_systemic_refill.py', 'systemic_transaction_helpers.py', 'systemic_cache_fill_ttl.json', 'systemic_forge_read_budget.json', 'systemic_relay_manifest.json', 'systemic_skill_journal_budget.json'), 'nox-control/systemic_relay_20261118/owner_eval_checkpoint_prepare.py': (), 'nox-control/systemic_relay_20261118/owner_systemic_reviewed_entry.py': ('reviewed_systemic_transaction_helpers.py', 'reviewed_cache_ttl_plan.json', 'reviewed_cache_ttl_payload.source', 'reviewed_forge_budget_plan.json', 'reviewed_forge_budget_payload.source', 'reviewed_skill_budget_plan.json', 'reviewed_skill_budget_payload.source'), 'nox-control/systemic_relay_20261118/next_pack_44368502183/package/native_publish_entry_d58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212.py': (), 'nox-control/systemic_relay_20261118/tooling/owner_nox_acceleration_entry.py': (), 'nox-control/systemic_relay_20261118/next_chat_review/package_v4/owner_chat_decomposition_embedded_entry.py': ()}
SCOPED_REPAIR_EXTRA_PATHS={'nox-control/owner_continuous_executor_install.py': ('nox-control/continuous_executor_20261118/assets/cw_test_nox_forge_language_task_coverage.py', 'nox-control/continuous_executor_20261118/assets/cw_test_nox_readonly_retry_backoff.py', 'nox-control/continuous_executor_20261118/assets/cw_test_nox_warm_cache_limit_contract.py', 'nox-control/continuous_executor_20261118/assets/cw_contract_510dbdec4dd2538ebeac.json', 'nox-control/continuous_executor_20261118/assets/cw_contract_9efad5217ab0e554a383.json', 'nox-control/continuous_executor_20261118/assets/cw_contract_683c5086d66e750d4ed1.json', 'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py', 'nox-control/continuous_executor_20261118/assets/continuous_dispatcher.py', 'nox-control/continuous_executor_20261118/assets/continuous_planner.py', 'nox-control/continuous_executor_20261118/assets/continuous_truth.py'), 'nox-control/owner_bounded_cpu_install.py': ('nox-control/complete_executor_budget_20261118/assets/bc_runtime_d5fb476f53e64d2014f2.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_6c67e567e669b993d016.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_2c83ec53f7ee7c2d76bc.py', 'nox-control/complete_executor_budget_20261118/assets/bc_runtime_294473d35d4870f50467.py'), 'nox-control/owner_project_runtime_update.py': ('nox-control/complete_executor_retries_20261118/assets/ru_runtime_fcb77cc59eb9a88dde68.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_84d54c647b0a63447aca.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_52e62a143d16f387899f.py', 'nox-control/complete_executor_retries_20261118/assets/ru_runtime_aa0dd1c8266106b599ce.py', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_a171fa7a94084a1f4b67.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_fa3d69e506d727295094.data', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_79b77425ff05d3337c2e.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_b980a61884965f4838f8.data', 'nox-control/complete_executor_retries_20261118/assets/ru_plans_dd24421576ae4160fa01.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_7e625acddd71fe95988e.data', 'nox-control/complete_executor_retries_20261118/assets/ru_blobs_4b06687bbad8fe6ab046.data', 'nox-control/complete_executor_retries_20261118/assets/ru_contracts_eece310e5608fa9c633d.data'), 'nox-control/owner_complete_executor_install.py': ('nox-control/complete_executor_20261118/assets/ce_runtime_2c4735938dacd2a062ed.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_71dd03dee52f1673c297.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_f6b2f98ac5c7c291ffef.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_687ea3b3548badf9b7ba.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_35b0e94f9c883da017e4.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_d0ff44d4752128c26779.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_119115603be6dba84121.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_7f18d69529582b65f7b8.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_126c77c1281b74676930.py', 'nox-control/complete_executor_20261118/assets/ce_runtime_485d4a4a571c434afb98.py', 'nox-control/complete_executor_20261118/assets/ce_baseline_bb2c543979ad58801d97.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_4d1274059d034bb9b96a.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d9ec6a8250a167d774ba.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_c676fdda4fa47d316eb1.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_8657ad367e6dd25b48ca.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_006fc038f43682fa36d2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d35064a3fc5707dfc174.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_66a6617d6f582876dbdc.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_e3b0c44298fc1c149afb.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_092db7d32a048c1706da.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_dc19594b45a7fae32bf9.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_b4ece67144248808a12c.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_21f8538fec15d39b4dbc.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_3efe025681c3a54cbfac.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_b3c5d26011400b110a1b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_f299d32099c25ea1822c.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_0fff97b7e758e3e43073.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_fd815f9a743bfcdf6e71.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_97c433b8893514f5812b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_fc5d6c564c651c2abc81.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_623bfb4ba2d28d3dd3db.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_9201bc3629682a577c80.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_d6042e38549360ace8f9.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_2860173d8d6ed7147af2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_970d6681ce5dc57156e2.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_6aa9265942695d2b54b3.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_8d2070c2f0819e7d1c2b.source', 'nox-control/complete_executor_20261118/assets/ce_baseline_60e28219f670a8449a56.source', 'nox-control/complete_executor_20261118/assets/ce_plans_283ff826ba1180398888.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_fa3d69e506d727295094.source', 'nox-control/complete_executor_20261118/assets/ce_plans_e7c99335a4a790202f22.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_f7b69405224c63868b76.source', 'nox-control/complete_executor_20261118/assets/ce_plans_de41f4de77a043c695fe.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_7e625acddd71fe95988e.source', 'nox-control/complete_executor_20261118/assets/ce_plans_67e819b4ff1b94cc5bdd.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_b980a61884965f4838f8.source', 'nox-control/complete_executor_20261118/assets/ce_plans_4037501920f2e9f3ea41.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_06940cb13bd568d4cfaa.source', 'nox-control/complete_executor_20261118/assets/ce_plans_9b80e2075b52602ac9e1.json', 'nox-control/complete_executor_20261118/assets/ce_blobs_f336c58fb5062aec6d5b.source', 'nox-control/complete_executor_20261118/assets/ce_contracts_b40696685ca2b7c848a2.json', 'nox-control/complete_executor_20261118/assets/ce_manifests_79a8efb2d344479471bd.json', 'nox-control/complete_executor_20261118/assets/ce_manifests_e040c40bd8ee3d29b0cc.json'), 'nox-control/owner_chat_markdown_asset_install_v2.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/nox-v24-chat-markdown-final.js'), 'nox-control/owner_chat_markdown_asset_install.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/nox-v24-chat-markdown-final.js'), 'nox-control/owner_workspace_browser_acceptance_v6.py': ('nox-control/owner_workspace_browser_acceptance_v5.py', 'nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_workspace_browser_acceptance_v5.py': ('nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_workspace_browser_acceptance_v3.py': ('nox-control/owner_workspace_browser_acceptance_v2.py', 'nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_qwen_successor_entry_v2.py': ('nox-control/owner_qwen_successor_install_v2.py', 'nox-control/owner_qwen_execution_successor.py', 'nox-control/qwen_student_training_entry_successor.py', 'nox-control/owner_qwen_successor_guard.py', 'nox-control/owner_qwen_successor_status.py', 'nox-control/owner_qwen_successor_media_handoff.py', 'nox-control/owner_qwen_successor_media_guard.py', 'nox-control/owner_qwen_successor_handback_retry.py', 'nox-control/owner_qwen_successor_hermes_hydrate.py', 'nox-control/owner_qwen_successor_watch.py'), 'nox-control/owner_workspace_browser_acceptance_v2.py': ('nox-control/owner_workspace_browser_acceptance.py', 'nox-control/owner_chat_page_diagnose.py'), 'nox-control/owner_qwen_successor_entry.py': ('nox-control/owner_qwen_successor_install.py', 'nox-control/owner_qwen_execution_successor.py', 'nox-control/qwen_student_training_entry_successor.py', 'nox-control/owner_qwen_successor_guard.py', 'nox-control/owner_qwen_successor_status.py', 'nox-control/owner_qwen_successor_media_handoff.py', 'nox-control/owner_qwen_successor_media_guard.py', 'nox-control/owner_qwen_successor_handback_retry.py', 'nox-control/owner_qwen_successor_hermes_hydrate.py', 'nox-control/owner_qwen_successor_watch.py'), 'nox-control/owner_workspace_browser_acceptance.py': ('nox-control/owner_chat_page_diagnose.py',), 'nox-control/owner_workspace_asset_install.py': ('nox-control/owner_chat_stream_asset_install_v2.py', 'coordination/onepass/workspace-owner-capabilities.js'), 'nox-control/owner_training_control_readonly_batch.py': ('nox-control/owner_qwen_transport_budget_observe.py', 'nox-control/owner_admin_control_structure_probe.py', 'nox-control/owner_qwen_public_memfd_access_probe.py'), 'nox-control/owner_chat_action_routing_install.py': ('nox-control/owner_chat_stream_action_routing.py',), 'nox-control/owner_chat_stream_asset_install_v2.py': ('coordination/onepass/nox-v135-resonance-owner-bridge-coalesced.js',), 'nox-control/owner_qwen_transport_rollback_entry.py': ('nox-control/owner_qwen_transport_rollback.py', 'nox-control/owner_qwen_transport_revision_install.py', 'nox-control/owner_qwen_transport_failed_diagnostic.json'), 'nox-control/owner_qwen_transport_budget_entry.py': ('nox-control/owner_qwen_transport_budget_install.py', 'nox-control/qwen_student_training_entry_transport_budget.py'), 'nox-control/owner_chat_stream_asset_install.py': ('coordination/onepass/nox-v135-resonance-owner-bridge-coalesced.js',), 'nox-control/owner_browser_asset_identity_entry.py': ('nox-control/owner_browser_normal_motion_entry.py', 'nox-control/owner_chat_normal_motion_qa.py', 'nox-control/owner_chat_asset_identity_qa.py'), 'nox-control/owner_qwen_held_media_smoke_v2_entry.py': ('nox-control/owner_qwen_held_media_smoke_v2.py',), 'nox-control/owner_browser_normal_motion_entry.py': ('nox-control/owner_chat_normal_motion_qa.py',), 'nox-control/owner_qwen_transport_install_entry.py': ('nox-control/owner_qwen_transport_revision_install.py', 'nox-control/qwen_student_training_entry_transport_candidate.py'), 'nox-control/owner_reviewed_rescue_catalog_append.py': ('nox-control/complete_executor_rescue_20261118/assets/rv_plan_379d1c5b50e42fb50165ce1fbe904cf47b1b45b3747878c60f9b1208d6e13e23.json', 'nox-control/complete_executor_rescue_20261118/assets/rv_payload_5201af0115e1ead68d3369794e33bbc97d7b7b2f00762c5c2ecfdaa7dda45926.source', 'nox-control/complete_executor_rescue_20261118/assets/rv_payload_4329f7389b24cfbb1fbb47c91b43eb7407bf18c95d15064fc7ea8166cde0a821.source'), 'nox-control/owner_kernel_self_fd_install.py': ('nox-control/complete_executor_proc_identity_20261118/assets/sf_runtime_192d0c1b7b87447d4f08.py', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_plan_457dbaf4484cfb5b7e14.json', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_payload_5201af0115e1ead68d33.source', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_payload_4329f7389b24cfbb1fbb.source', 'nox-control/complete_executor_proc_identity_20261118/assets/sf_fd_descriptor_768d28516014a124a380.json'), 'nox-control/owner_reviewed_proc_followup_catalog_append.py': ('nox-control/complete_executor_followup_20261118/assets/fu_plan_3f620116ee563127d7e94bfeac7aae1408aaa4f1752f431fee774c49023e6509.json', 'nox-control/complete_executor_followup_20261118/assets/fu_payload_a71051c085f8bfdbeda93f3f4c16501444ca35942ac4ca7f3a46d7bd16acfbbc.source', 'nox-control/complete_executor_followup_20261118/assets/fu_payload_f5c8eb6b42e71efa38745bc6f729a989b4a199999d7c3b9aa45cebbde36f851a.source'), 'nox-control/owner_model_slot_recovery.py': ('nox-control/model_slot_recovery_20261118/assets/slot_contract_3f43e152774c159bbe45.json', 'nox-control/model_slot_recovery_20261118/assets/slot_contract_60a6abf6691f6c3fb186.json', 'nox-control/model_slot_recovery_20261118/assets/slot_transaction_helpers.py', 'nox-control/model_slot_recovery_20261118/assets/slot_model_client.py'), 'nox-control/owner_c02_memory_progress_install.py': ('nox-control/c02_memory_progress_20261118/assets/c02_contract_4a8f20c371f3211c2351.json', 'nox-control/c02_memory_progress_20261118/assets/c02_test_nox_c02_existing_cognition.py', 'nox-control/c02_memory_progress_20261118/assets/c02_test_nox_c02_optional_starvation.py', 'nox-control/c02_memory_progress_20261118/assets/c02_transaction_helpers.py'), 'nox-control/owner_c02_memory_reviewed_recovery.py': ('nox-control/c02_memory_progress_20261118/recovery_assets/c02r_payload_b504248ac1ae4a093382.source', 'nox-control/c02_memory_progress_20261118/recovery_assets/c02r_plan_5d05ba50d058981ce8ba.json', 'nox-control/c02_memory_progress_20261118/recovery_assets/c02r_transaction_helpers.py'), 'nox-control/systemic_relay_20261118/owner_systemic_relay_entry.py': ('nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_dispatcher.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_processes.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_project_native.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_project_planner.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_subagent_instruction_truth.py', 'nox-control/systemic_relay_20261118/assets/systemic_owner_systemic_refill.py', 'nox-control/systemic_relay_20261118/assets/systemic_transaction_helpers.py', 'nox-control/systemic_relay_20261118/assets/systemic_cache_fill_ttl.json', 'nox-control/systemic_relay_20261118/assets/systemic_forge_read_budget.json', 'nox-control/systemic_relay_20261118/assets/systemic_relay_manifest.json', 'nox-control/systemic_relay_20261118/assets/systemic_skill_journal_budget.json'), 'nox-control/systemic_relay_20261118/owner_eval_checkpoint_prepare.py': (), 'nox-control/systemic_relay_20261118/owner_systemic_reviewed_entry.py': ('nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_systemic_transaction_helpers.py', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_cache_ttl_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_cache_ttl_payload.source', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_forge_budget_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_forge_budget_payload.source', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_skill_budget_plan.json', 'nox-control/systemic_relay_20261118/reviewed_recovery/assets/reviewed_skill_budget_payload.source')}

FROZEN_BROWSER_PAGE_DEPENDENCIES={
    'owner_browser_stream_only_entry.py':'nox-control/pinned/browser_normal_v1/owner_browser_stream_only_entry.py',
}
SCOPED_REPAIR_BUNDLES[FILES['repair']] = ()
SCOPED_REPAIR_EXTRA_PATHS[FILES['repair']] = ()
FROZEN_BROWSER_DEPENDENCIES={
    'owner_browser_stream_only_entry.py':'nox-control/pinned/browser_normal_v1/owner_browser_stream_only_entry.py',
    'owner_chat_stream_only_qa.py':'nox-control/pinned/browser_normal_v1/owner_chat_stream_only_qa.py',
}
FROZEN_BROWSER_ENTRIES=('nox-control/owner_browser_normal_motion_entry.py',
                        'nox-control/owner_browser_asset_identity_entry.py')

def repair_bundle_paths(action,entrypoint,paths):
    if action!='repair' or entrypoint not in SCOPED_REPAIR_BUNDLES:return paths
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
    source_sha=os.environ.get('NOX_PINNED_SOURCE_SHA','')
    forwarded=forward_remote_stdout(r.stdout,action,int(request_id),source_sha)
    for line in forwarded:print(line,flush=True)
    print('NOX_MAINT_REMOTE_EXIT_CODE='+str(r.returncode),flush=True)
    if r.returncode:
        err=r.stderr.lower()
        cls='AUTH' if 'permission denied' in err else 'TIMEOUT' if 'timed out' in err else 'CONNECTION' if 'connect' in err else 'PAYLOAD'
        print('NOX_MAINT_FAILURE_CLASS='+cls,flush=True)
    marker='NOX_MAINT_'+action.upper()+'_COMPLETE=true'
    if r.returncode or marker not in r.stdout:raise RuntimeError('HOLD_NATIVE_PAYLOAD_INCOMPLETE')
    if action=='audit':
        gate=audit_census_status(r.stdout)
        print('NOX_MAINT_AUDIT_CENSUS_GATE='+json.dumps(gate,separators=(',',':'),sort_keys=True),flush=True)
        require_audit_census_complete(r.stdout)
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
