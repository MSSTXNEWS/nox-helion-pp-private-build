#!/usr/bin/env python3
"""Finite read-only follow-up for NOX's previously opaque SSD allocation.

No deletion, alias change, upload, model/control operation, or background daemon.
The only write is one exclusive mode-0600 audit receipt in existing owner state.
Unknown filenames and paths are retained only there, never in public output.
"""
from __future__ import annotations

import base64
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import time
import types
import urllib.request

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
SHM = Path('/dev/shm')
CGROUP = Path('/sys/fs/cgroup')
PROC = Path('/proc')
HELPER_SHA = '1d6d89844a4402288dc812b7a1f38abb90521a7af00a1d83d29409cb5a9c0b9c'
SCHEMA = 'NOX_OWNER_REMAINING_STORAGE_AUDIT_V1'
INSTANCE = 60509551
GIB = 1024**3
TOP_N = 24
MAX_ENTRIES = 70000
MAX_DIRS = 8000
MAX_DEPTH = 20
TOTAL_SECONDS = 55
WALK_SECONDS = 12
HASH_SECONDS = 22
HASH_RATE = 32*1024**2
BUILDER_BYTES = 306787336
BUILDER_SHA = '3030a2623b279ec0586bbdf403cf7ee13a32bd0fe2bf5094538d59b7c854ddb9'
BUILDER_PATHS = (
    ROOT/'progress_pull_t784u/workspace-2-2/nox_jp_backup_20261113/nox/state/stage3/builder/best_holdout/adapter_model.safetensors',
    ROOT/'progress_pull_t784u/workspace-2-2/nox36/ckpt/builder_best_holdout_kept/adapter_model.safetensors',
)
HF_BASE = ROOT/'progress_pull_t784u/workspace-2-2/nox36/ckpt/final/merged_hf'
TRAIN_OUTPUT = ROOT/'lora/qlora_t866u/runs_owner_hybrid'
MEDIA_FILES = {
    'sdxl_lightning_4step.safetensors':6938040682,
    'wan2.1_t2v_1.3B_fp16.safetensors':2838303560,
    'umt5_xxl_fp8_e4m3fn_scaled.safetensors':6735906897,
    'wan_2.1_vae.safetensors':253815318,
}
ADAPTER_FILES = ('t724u_builder_best_holdout.safetensors', 't724u_core_self_final.safetensors',
                 't724u_intellect_best_holdout.safetensors')
SENSITIVE = {'pc_shell','secrets','credentials','.ssh','.git'}
PUBLIC_GROUPS = {'progress_pull_t784u':'LEGACY_PULL_784','progress_pull_pc_t809u':'PC_IMPORT_809',
                 'tmp':'OWNED_TEMP','logs':'NOX_LOGS'}
ARCHIVE_SUFFIX = {'.zip','.tar','.gz','.xz','.zst','.7z','.tgz','.bz2'}


class AuditHold(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise AuditHold(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def helper_module():
    raw = base64.b64decode(BUNDLE.get('owner_storage_reclaim.py',''),validate=True)
    require(0<len(raw)<=262144 and digest(raw)==HELPER_SHA,'HOLD_REMAINING_STORAGE_HELPER_PIN')
    module = types.ModuleType('reviewed_storage_readonly_primitives')
    exec(compile(raw,'<pinned-storage-readonly-primitives>','exec'),module.__dict__)
    module.ROOT=ROOT
    return module


def stable_read(path, maximum=262144):
    path=Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (path,*path.parents)), 'HOLD_AUDIT_PATH')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0<=before.st_size<=maximum,'HOLD_AUDIT_FILE_TYPE_OR_SIZE')
        raw=os.read(fd,maximum+1)
        after=os.fstat(fd);named=path.stat(follow_symlinks=False)
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
        require(len(raw)==before.st_size and all(getattr(before,k)==getattr(after,k)==getattr(named,k) for k in fields),
                'HOLD_AUDIT_FILE_CHANGED')
        return raw,before
    finally:
        os.close(fd)


def read_json(path, maximum=262144):
    raw,info=stable_read(path,maximum)
    value=json.loads(raw)
    require(isinstance(value,dict),'HOLD_AUDIT_JSON_SCHEMA')
    return value,digest(raw),info


def pseudo_bytes(path, maximum):
    """Known proc/cgroup pseudo-files report size zero; read only a fixed cap."""
    path=Path(path)
    require(path.is_relative_to(PROC) or path.is_relative_to(CGROUP),'HOLD_PSEUDO_SCOPE')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd);require(stat.S_ISREG(info.st_mode),'HOLD_PSEUDO_TYPE')
        raw=os.read(fd,maximum+1);require(len(raw)<=maximum,'HOLD_PSEUDO_SIZE');return raw
    finally:os.close(fd)


def identity(info):
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_nlink,info.st_uid]


def path_id(path):
    return digest(str(path).encode())[:24]


def kind(path, helper):
    parts={item.casefold() for item in path.parts}
    if helper.PARTIAL.search(path.name):return 'DOWNLOAD_OR_MUTABLE_PARTIAL_PROTECTED'
    if (parts & {'ckpt','checkpoint','checkpoints','state','memory','memories','s03','lora','distill','datasets','data'}
            or any(item.casefold().startswith('checkpoint-') for item in path.parts)):
        return 'LEGACY_STATE_CORPUS_CHECKPOINT_PROTECTED'
    if path.suffix.casefold() in helper.WEIGHT_SUFFIX:return 'LEGACY_MODEL_WEIGHTS_PROTECTED'
    allowed=helper.deletion_kind(path)
    if allowed:return allowed[0]
    if path.suffix.casefold() in ARCHIVE_SUFFIX:return 'ARCHIVE_PACKAGE_PROTECTED'
    if parts & {'site-packages','node_modules','bin','lib','include'} or any('venv' in item for item in parts):
        return 'RUNTIME_ENVIRONMENT_PROTECTED'
    if (parts & {'scripts','src','source','config','configs'}
            or path.suffix.casefold() in {'.py','.js','.json','.yaml','.yml','.toml','.ini','.conf','.sqlite','.db','.jsonl'}):
        return 'SOURCE_CONFIG_HISTORY_PROTECTED'
    if '.log' in path.name.casefold():return 'LOG_NOT_APPROVED_FOR_RECLAIM'
    return 'OTHER_REGULAR_PROTECTED'


def metadata_row(path, info, helper):
    try:
        relative=path.relative_to(ROOT)
        group=PUBLIC_GROUPS.get(relative.parts[0],'OTHER_ROOT_ENTRY')
        group_path=ROOT/relative.parts[0]
    except ValueError:
        group='SUPERVISOR_LOGS';group_path=path.parent
    return {'path':str(path),'file_id':path_id(path),'group_id':path_id(group_path),'group':group,
        'kind':kind(path,helper),'identity':identity(info),'logical_bytes':info.st_size,
        'allocated_bytes':info.st_blocks*512,'link_count':info.st_nlink,
        'age_seconds':max(0,int(time.time()-max(info.st_mtime,info.st_ctime)))}


def walk_remaining(helper, deadline):
    """Skip the already explained HF/chat/state/env scopes; never follow links."""
    counts=Counter();totals=defaultdict(Counter);group_totals=defaultdict(Counter)
    seen=set();largest=[];ephemeral=[];coverage=[]
    for label,root in (('NOX_OTHER',ROOT),('NOX_LOGS',ROOT/'logs'),('SUPERVISOR_LOGS',Path('/var/log/supervisor'))):
        observed={'scope':label,'complete':True,'entries':0,'directories':0}
        coverage.append(observed)
        try:
            helper.plain(root);initial=root.stat()
            require(stat.S_ISDIR(initial.st_mode),'HOLD_AUDIT_ROOT_TYPE')
        except FileNotFoundError:
            observed['state']='ABSENT';continue
        except (OSError,AuditHold,helper.StorageHold):
            observed.update(state='UNKNOWN_ROOT',complete=False);continue
        pending=[(root,0)]
        while pending:
            if time.monotonic()>deadline or counts['entries']>=MAX_ENTRIES or counts['directories']>=MAX_DIRS:
                observed.update(complete=False,state='BOUNDED_PARTIAL');break
            directory,depth=pending.pop();counts['directories']+=1;observed['directories']+=1
            try:
                with os.scandir(directory) as entries:
                    for item in entries:
                        if time.monotonic()>deadline or counts['entries']>=MAX_ENTRIES:
                            observed.update(complete=False,state='BOUNDED_PARTIAL');break
                        counts['entries']+=1;observed['entries']+=1;path=Path(item.path)
                        try:
                            info=item.stat(follow_symlinks=False)
                            if stat.S_ISLNK(info.st_mode):counts['symlinks_not_followed']+=1;continue
                            if info.st_dev!=initial.st_dev:counts['other_mounts_not_crossed']+=1;continue
                            if stat.S_ISDIR(info.st_mode):
                                if path.name.casefold() in SENSITIVE:
                                    counts['sensitive_directories_excluded']+=1;continue
                                if label=='NOX_OTHER' and helper.category('NOX',path)!='NOX_OTHER_PROTECTED':
                                    counts['previously_classified_directories_excluded']+=1;continue
                                if depth>=MAX_DEPTH:
                                    counts['depth_exclusions']+=1;observed['complete']=False
                                else:pending.append((path,depth+1))
                                continue
                            if not stat.S_ISREG(info.st_mode):counts['special_files_not_read']+=1;continue
                            if label=='NOX_OTHER' and helper.category('NOX',path)!='NOX_OTHER_PROTECTED':continue
                            row=metadata_row(path,info,helper);key=(info.st_dev,info.st_ino)
                            bucket=totals[row['kind']];bucket['paths']+=1
                            if key in seen:
                                bucket['repeated_inode_paths']+=1;continue
                            seen.add(key);bucket['unique_inodes']+=1
                            bucket['logical_bytes']+=info.st_size;bucket['allocated_bytes']+=info.st_blocks*512
                            group=group_totals[(row['group'],row['group_id'])]
                            group['unique_inodes']+=1;group['allocated_bytes']+=row['allocated_bytes']
                            largest.append(row)
                            if len(largest)>TOP_N*2:
                                largest=sorted(largest,key=lambda x:x['allocated_bytes'],reverse=True)[:TOP_N]
                            if helper.deletion_kind(path) and len(ephemeral)<128:
                                ephemeral.append(row)
                        except (OSError,AuditHold,helper.StorageHold):
                            counts['unreadable_entries']+=1;observed['complete']=False
            except OSError:
                counts['unreadable_directories']+=1;observed['complete']=False
        observed.setdefault('state','OBSERVED_METADATA_ONLY' if observed['complete'] else 'BOUNDED_PARTIAL')
    groups=[{'group':key[0],'group_id':key[1],**dict(value)} for key,value in group_totals.items()]
    return {'coverage':coverage,'counts':dict(counts),'categories':{k:dict(v) for k,v in totals.items()},
        'groups':sorted(groups,key=lambda x:x['allocated_bytes'],reverse=True)[:12],
        'largest':sorted(largest,key=lambda x:x['allocated_bytes'],reverse=True)[:TOP_N],
        'ephemeral':ephemeral,'allocation_basis':'ST_BLOCKS_PER_DEVICE_AND_INODE_NOT_REFLINK_EXTENT_PROOF'}


def hash_builder(path, deadline, helper):
    helper.plain(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size==BUILDER_BYTES and before.st_uid==os.geteuid()
                and not before.st_mode & 0o022,'HOLD_BUILDER_FILE_IDENTITY')
        h=hashlib.sha256();read=0;started=time.monotonic()
        while read<before.st_size:
            require(time.monotonic()<deadline,'HOLD_BUILDER_HASH_TIME_BUDGET')
            raw=os.read(fd,min(1024**2,before.st_size-read))
            require(bool(raw),'HOLD_BUILDER_UNEXPECTED_EOF');h.update(raw);read+=len(raw)
            delay=read/HASH_RATE-(time.monotonic()-started)
            if delay>0:time.sleep(min(delay,.04))
        after=os.fstat(fd);named=path.stat(follow_symlinks=False)
        require(identity(before)==identity(after)==identity(named),'HOLD_BUILDER_CHANGED_DURING_READ')
        require(h.hexdigest()==BUILDER_SHA,'HOLD_BUILDER_FULL_SHA_MISMATCH')
        return {'path':str(path),'file_id':path_id(path),'identity':identity(before),'sha256':BUILDER_SHA,
                'bytes':read,'allocated_bytes':before.st_blocks*512,'full_sha_verified':True}
    finally:
        os.close(fd)


def duplicate_proof(helper, deadline):
    rows=[];blockers=[]
    for path in BUILDER_PATHS:
        try:rows.append(hash_builder(path,deadline,helper))
        except (OSError,AuditHold,helper.StorageHold) as exc:
            code=str(exc)
            blockers.append(code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else 'HOLD_BUILDER_READ_UNAVAILABLE')
    return {'files':rows,'blockers':blockers,'bytes_read':sum(row['bytes'] for row in rows),
            'sha256':BUILDER_SHA,'same_bytes_verified':len(rows)==2 and not blockers,
            'files_deleted':0,'paths_or_configs_changed':False}


def combined_usage(before, after):
    return {'complete':before['complete'] and after['complete'],'used':before['used']|after['used'],
            'active_package_manager':before['active_package_manager'] or after['active_package_manager']}


def qualify_results(scan, duplicate, usage, helper):
    eligible=[];refusals=Counter()
    for row in scan['ephemeral']:
        path=Path(row['path'])
        try:
            helper.plain(path);info=path.stat(follow_symlinks=False)
            require(identity(info)==row['identity'],'HOLD_EPHEMERAL_IDENTITY_CHANGED')
            candidate,reason=helper.qualify(path,info,time.time(),usage)
            if candidate:eligible.append(candidate)
            else:refusals[reason]+=1
        except (OSError,AuditHold,helper.StorageHold):refusals['IDENTITY_OR_READ_UNVERIFIED']+=1
    for row in scan['largest']:
        row['active_reference_observed']=(row['identity'][0],row['identity'][1]) in usage['used']
        row['absence_of_active_reference_verified']=usage['complete'] and not row['active_reference_observed']
    rows=duplicate['files'];keys={(row['identity'][0],row['identity'][1]) for row in rows}
    for row in rows:
        try:
            path=helper.plain(Path(row['path']))
            require(identity(path.stat(follow_symlinks=False))==row['identity'],'HOLD_BUILDER_IDENTITY_CHANGED_AFTER_HASH')
        except (OSError,AuditHold,helper.StorageHold):duplicate['blockers'].append('BUILDER_IDENTITY_CHANGED_AFTER_HASH')
    duplicate['distinct_ssd_inodes']=len(keys)
    if not usage['complete']:duplicate['blockers'].append('PROCESS_INSPECTION_INCOMPLETE')
    if any(key in usage['used'] for key in keys):duplicate['blockers'].append('OPEN_OR_MEMORY_MAPPED')
    if len(rows)==2 and rows[0]['identity'][0]!=rows[1]['identity'][0]:duplicate['blockers'].append('DIFFERENT_FILESYSTEMS')
    if any(row['identity'][5]!=1 for row in rows):duplicate['blockers'].append('EXISTING_HARDLINKS_REQUIRE_SEPARATE_REVIEW')
    duplicate['reviewable_retained_copy_dedup']=bool(duplicate['same_bytes_verified'] and len(keys)==2 and not duplicate['blockers'])
    duplicate['maximum_duplicate_allocated_bytes']=min((row['allocated_bytes'] for row in rows),default=0) if len(keys)==2 else 0
    duplicate['retained_full_ssd_copy_required']=True
    duplicate['original_weight_paths_must_remain_resolvable']=True
    duplicate['all_configs_and_provenance_must_be_preserved']=True
    duplicate['automatic_deletion_authorized']=False
    return eligible,dict(refusals)


def metadata(path, helper, allow_alias=False):
    path=Path(path)
    if allow_alias and path.is_symlink():
        target=path.resolve(strict=True)
        require(target.is_relative_to(ROOT),'HOLD_ACTIVE_ALIAS_SCOPE');path=target
    helper.plain(path);info=path.stat(follow_symlinks=False)
    require(stat.S_ISREG(info.st_mode),'HOLD_PLACEMENT_FILE_TYPE')
    return {'logical_bytes':info.st_size,'allocated_bytes':info.st_blocks*512,'identity':identity(info)}


def protected_placement(helper, usage):
    budget=helper.filesystem_budget()
    shm_device=SHM.stat().st_dev
    try:
        raw=pseudo_bytes(CGROUP/'memory.peak',128)
        peak=int(raw);require(peak>=0,'HOLD_PEAK_VALUE')
    except (OSError,ValueError,AuditHold):peak=None
    budget['cgroup']['peak_bytes']=peak
    limit=budget['cgroup'].get('limit_bytes');current_headroom=budget['cgroup'].get('headroom_bytes',0)
    peak_headroom=max(0,limit-peak) if type(limit) is int and type(peak) is int else None
    base=Counter();base_seen=set();base_complete=True
    try:
        helper.plain(HF_BASE)
        with os.scandir(HF_BASE) as items:
            for count,item in enumerate(items):
                if count>=128:base_complete=False;break
                info=item.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino) not in base_seen:
                    base_seen.add((info.st_dev,info.st_ino));base['logical_bytes']+=info.st_size;base['allocated_bytes']+=info.st_blocks*512;base['files']+=1
                elif stat.S_ISLNK(info.st_mode):base_complete=False
    except OSError:base_complete=False
    active=[]
    for label,path in (('CHAT_GGUF',ROOT/'models/current.gguf'),('BGE_EMBEDDINGS',ROOT/'models/bge-m3-Q4_K_M.gguf'),
                       ('TEACHER_ALIAS',ROOT/'models/teachers_ondisk/current.gguf')):
        try:
            row=metadata(path,helper,True);key=tuple(row['identity'][:2])
            active.append({'label':label,**row,'mapped_or_open':key in usage['used']})
        except (OSError,AuditHold,helper.StorageHold):active.append({'label':label,'state':'UNVERIFIED'})
    media=[]
    try:
        config,_,_=read_json(ROOT/'config/owner_media_runtime.json')
        rows=config.get('assets',[])
        require(isinstance(rows,list) and len(rows)<=12,'HOLD_MEDIA_ASSET_SCHEMA')
        for row in rows:
            if not isinstance(row,dict) or row.get('filename') not in MEDIA_FILES:continue
            path=Path(row.get('path',''));require(path.is_absolute() and path.is_relative_to(SHM),'HOLD_MEDIA_RAM_SCOPE')
            info=metadata(path,helper)
            if info['logical_bytes']!=MEDIA_FILES[row['filename']] or info['identity'][0]!=shm_device:continue
            media.append({'asset':row['filename'],'bytes':info['logical_bytes'],'allocated_bytes':info['allocated_bytes'],
                          'historical_config_verified_flag':row.get('verified') is True,
                          'current_mtime_matches_config':row.get('stat_mtime_ns')==info['identity'][3],
                          'full_sha_recomputed':False})
    except (OSError,ValueError,AuditHold,helper.StorageHold):pass
    adapters=[]
    for name in ADAPTER_FILES:
        try:
            row=metadata(SHM/'nox_drive/3t724u'/name,helper)
            require(row['identity'][0]==shm_device,'HOLD_ADAPTER_RAM_DEVICE')
            adapters.append({'role':name.removeprefix('t724u_').removesuffix('.safetensors'),
                'bytes':row['logical_bytes'],'allocated_bytes':row['allocated_bytes'],'full_sha_recomputed':False})
        except (OSError,AuditHold,helper.StorageHold):pass
    try:corpus=metadata(TRAIN_OUTPUT/'training_text.jsonl',helper)
    except (OSError,AuditHold,helper.StorageHold):corpus={'state':'UNVERIFIED'}
    checkpoints=Counter();checkpoint_complete=True
    try:
        helper.plain(TRAIN_OUTPUT)
        with os.scandir(TRAIN_OUTPUT) as items:
            for count,item in enumerate(items):
                if count>=2048:checkpoint_complete=False;break
                if item.name.startswith('checkpoint-') and item.is_dir(follow_symlinks=False):
                    checkpoints['checkpoint_directories']+=1
                elif item.name.startswith('owner_receipt_step_') and item.is_file(follow_symlinks=False):
                    checkpoints['step_receipts']+=1
    except OSError:checkpoint_complete=False
    ram_admission=max(0,min(budget['tmpfs']['free_bytes']-3*GIB,current_headroom-16*GIB,
                            (peak_headroom-16*GIB) if peak_headroom is not None else 0))
    return {'budget':budget,'peak_headroom_bytes':peak_headroom,
        'peak_scope':'CGROUP_LIFETIME_PEAK_NOT_ATTRIBUTED_SOLELY_TO_CURRENT_TRAINER',
        'hf_base':dict(base,coverage_complete=base_complete,policy='KEEP_SSD_NO_REDUNDANT_FULL_TMPFS_COPY'),
        'chat_gguf_policy':'KEEP_EXISTING_SSD_FILE_AND_OS_PAGE_CACHE',
        'active_models':active,'media_ram_metadata':media,'media_ram_bytes':sum(row['bytes'] for row in media),
        'adapter_ram_metadata':adapters,'adapter_ram_bytes':sum(row['bytes'] for row in adapters),
        'protected_training_corpus':corpus,'protected_checkpoints':dict(checkpoints,coverage_complete=checkpoint_complete),
        'conservative_new_ram_admission_bytes':ram_admission,
        'full_training_base_fits_additional_ram':bool(base_complete and base.get('logical_bytes',0)>0 and base['logical_bytes']<=ram_admission),
        'ram_reclaim_is_ssd_reclaim':False,'ram_is_durable_backup':False,
        'warm_storage':{'autonomous_drive_upload_verified':False,'direct_drive_api_check_performed':False,
            'state':'REQUIRES_NATIVE_AUTH_CAPACITY_AND_FULL_SHA_READBACK',
            'unique_weight_eviction_allowed':False,'required_independent_copies':['PC_SHA_VERIFIED','DRIVE_SHA_VERIFIED'],
            'training_corpus_and_new_checkpoints_protected':True,'transfers_started':0},
        'files_deleted':0,'model_moved':False,'services_changed':False}


def slot_projection(value):
    require(isinstance(value,list) and 1<=len(value)<=16,'HOLD_SLOT_SCHEMA')
    rows=[]
    for row in value:
        require(isinstance(row,dict) and type(row.get('id')) is int and 0<=row['id']<64,'HOLD_SLOT_SCHEMA')
        flags=[row[key] for key in ('is_processing','processing') if key in row]
        require(flags and all(type(flag) is bool for flag in flags) and len(set(flags))==1,'HOLD_SLOT_BUSY_UNVERIFIED')
        projected={'id':row['id'],'busy':flags[0]}
        for key in ('id_task','n_ctx','n_past','n_decoded','n_prompt_tokens','n_predicted_tokens','t_last_used'):
            number=row.get(key)
            if type(number) in (int,float) and math.isfinite(number):projected[key]=number
        timing=row.get('timings')
        if isinstance(timing,dict):
            projected['timings']={key:timing[key] for key in ('prompt_ms','predicted_ms','prompt_n','predicted_n')
                if type(timing.get(key)) in (int,float) and math.isfinite(timing[key])}
        rows.append(projected)
    require(len({row['id'] for row in rows})==len(rows),'HOLD_SLOT_DUPLICATE_ID')
    return {'state':'OBSERVED','slots':rows,'total':len(rows),'busy':sum(row['busy'] for row in rows)}


KNOWN_PROGRAMS={
    '/root/nox/scripts/chat_proxy.py':'NOX_CHAT_PROXY',
    '/root/nox/scripts/nox_dispatcher_t855u.py':'NOX_DISPATCHER',
    '/root/nox/scripts/dialog_miner.py':'NOX_DIALOG_MINER',
    '/root/nox/scripts/nox_cores_t899u.py':'NOX_CORES',
    '/root/nox/scripts/checklist_worker.py':'NOX_CHECKLIST',
    '/root/nox/scripts/nox_agent_integrator_t859u.py':'NOX_INTEGRATOR',
    '/root/nox/scripts/nox_agent_architect_t859u.py':'NOX_ARCHITECT',
    '/root/nox/scripts/nox_agent_tuner_t858u.py':'NOX_TUNER',
    '/root/nox/scripts/nox_priority_scheduler.py':'NOX_PRIORITY',
    '/root/nox_selfheal.py':'NOX_SELFHEAL',
}


def socket_rows(raw):
    result=[]
    for line in raw.splitlines()[1:]:
        fields=line.split()
        if len(fields)<10 or fields[3]!=b'01':continue
        endpoints=[]
        try:
            for endpoint in fields[1:3]:
                addr,port=endpoint.decode('ascii').split(':')
                octets=bytes.fromhex(addr)
                octets=b''.join(octets[i:i+4][::-1] for i in range(0,len(octets),4))
                address=ipaddress.ip_address(octets)
                endpoints.append((address.is_loopback or bool(getattr(address,'ipv4_mapped',None) and address.ipv4_mapped.is_loopback),int(port,16)))
            # Capture client-side sockets only; the server PID alone is not a
            # request initiator. Remote IP/address/port strings are discarded.
            if endpoints[0][0] and endpoints[1][0] and endpoints[1][1]==8081 and endpoints[0][1]!=8081:
                inode=int(fields[9]);require(inode>0,'HOLD_TCP_INODE')
                result.append({'socket_inode':inode,'owners':[]})
        except (ValueError,UnicodeError,AuditHold):continue
        if len(result)>=32:break
    return result


def tcp_clients(deadline):
    rows=[];counts=Counter();complete=True
    try:
        for name in ('tcp','tcp6'):
            rows.extend(socket_rows(pseudo_bytes(PROC/str(os.getpid())/'net'/name,2*1024**2)))
        rows=rows[:32];by_inode={row['socket_inode']:row for row in rows}
        if not rows:return {'state':'NO_LOCAL_CLIENT_CONNECTION_OBSERVED','clients':[],'complete':True}
        with os.scandir(PROC) as items:pids=[item.name for item in items if item.name.isdigit()]
        require(len(pids)<=2048,'HOLD_TCP_PROCESS_BUDGET')
        for pid in pids:
            if time.monotonic()>deadline or counts['fds']>=40000:complete=False;break
            try:
                owned=set()
                with os.scandir(PROC/pid/'fd') as fds:
                    for item in fds:
                        counts['fds']+=1
                        if time.monotonic()>deadline or counts['fds']>=40000:complete=False;break
                        try:target=os.readlink(item.path)
                        except FileNotFoundError:continue
                        match=re.fullmatch(r'socket:\[(\d+)\]',target)
                        if match and int(match[1]) in by_inode:owned.add(int(match[1]))
                if owned:
                    args=pseudo_bytes(PROC/pid/'cmdline',8192).split(b'\0')
                    label=next((name for script,name in KNOWN_PROGRAMS.items() if script.encode() in args),'UNKNOWN_PROGRAM')
                    if int(pid)==os.getpid():label='THIS_READ_ONLY_AUDIT'
                    for inode in owned:
                        if len(by_inode[inode]['owners'])>=8:complete=False;continue
                        by_inode[inode]['owners'].append({'pid':int(pid),'known_program':label,
                            'identity_scope':'EXACT_KNOWN_ARGV_MATCH_NOT_REQUEST_AUTHENTICATION'})
            except (FileNotFoundError,ProcessLookupError):continue
            except (OSError,AuditHold):counts['unreadable_processes']+=1;complete=False
        return {'state':'LOCAL_CLIENT_CONNECTION_METADATA','clients':rows,'complete':complete,
            'counts':dict(counts),'request_origin_scope':'PROXY_SOCKET_CANNOT_SEPARATE_OWNER_AND_BACKGROUND_REQUESTS'}
    except (OSError,AuditHold):return {'state':'UNKNOWN_TCP_CLIENT_METADATA','clients':rows,'complete':False}


def slot_samples():
    samples=[];start=time.monotonic()
    for index in range(2):
        if index:
            delay=8-(time.monotonic()-start)
            if delay>0:time.sleep(delay)
        row={'sample':index,'observed_at':time.time()}
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:8081/slots',timeout=2) as response:
                raw=response.read(100001)
            require(len(raw)<=100000,'HOLD_SLOT_BYTES')
            row.update(slot_projection(json.loads(raw)))
        except Exception:
            row.update(state='UNKNOWN_SLOT_METADATA',busy=None,total=None)
        row['clients']=tcp_clients(time.monotonic()+1)
        samples.append(row)
    return {'samples':samples,'elapsed_seconds':round(time.monotonic()-start,3),
        'inference_requests_sent':0,'prompts_or_raw_slots_exported':False,'processes_stopped':0}


def public_summary(receipt):
    value={key:receipt[key] for key in ('schema','instance_id','request','source_sha','state','started_at','finished_at',
        'coverage','counts','categories','groups','allocation_basis','process_scans','cleanup_refusals',
        'eligible_ephemeral_allocated_bytes','placement','files_deleted','training_control_performed')}
    value['model_client_observation']=receipt['model_client_observation']
    value['largest']=[{k:v for k,v in row.items() if k not in ('path','identity')} for row in receipt['largest']]
    value['ephemeral_candidates']=[{'file_id':row['path_id'],'category':row['category'],'allocated_bytes':row['allocated_bytes']}
                                   for row in receipt['ephemeral_candidates']]
    duplicate=receipt['builder_duplicate']
    value['builder_duplicate']={k:v for k,v in duplicate.items() if k!='files'}
    value['builder_duplicate']['files']=[{k:v for k,v in row.items() if k not in ('path','identity')} for row in duplicate['files']]
    value['unknown_filenames_or_private_text_exported']=False
    return value


def write_receipt(helper, request, value):
    directory=helper.receipt_directory();path=helper.plain(directory/('remaining_'+request+'.json'))
    raw=(json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False)+'\n').encode()
    require(len(raw)<=2*1024**2,'HOLD_REMAINING_RECEIPT_SIZE')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return str(path),digest(raw)


def run(request, source):
    require(bool(re.fullmatch('[0-9]{1,24}',request)) and bool(re.fullmatch('[a-f0-9]{40}',source)), 'HOLD_OWNER_CONTEXT')
    helper=helper_module();started=time.time();deadline=time.monotonic()+TOTAL_SECONDS
    with ThreadPoolExecutor(max_workers=1) as pool:
        slots=pool.submit(slot_samples)
        before=helper.process_usage(min(deadline,time.monotonic()+5))
        scan=walk_remaining(helper,min(deadline,time.monotonic()+WALK_SECONDS))
        duplicate=duplicate_proof(helper,min(deadline-6,time.monotonic()+HASH_SECONDS))
        after=helper.process_usage(min(deadline,time.monotonic()+5));usage=combined_usage(before,after)
        candidates,refusals=qualify_results(scan,duplicate,usage,helper)
        placement=protected_placement(helper,usage)
        client_observation=slots.result()
    record={'schema':SCHEMA,'instance_id':INSTANCE,'request':request,'source_sha':source,
        'state':'READ_ONLY_ALLOCATION_AND_DUPLICATE_AUDIT','started_at':started,'finished_at':time.time(),
        **{k:v for k,v in scan.items() if k!='ephemeral'},
        'process_scans':[{k:v for k,v in value.items() if k!='used'} for value in (before,after)],
        'ephemeral_candidates':candidates,'cleanup_refusals':refusals,
        'eligible_ephemeral_allocated_bytes':sum(row['allocated_bytes'] for row in candidates),
        'builder_duplicate':duplicate,'placement':placement,'model_client_observation':client_observation,
        'files_deleted':0,'training_control_performed':False}
    path,sha=write_receipt(helper,request,record)
    public=public_summary(record);public.update(receipt_path=path,receipt_sha256=sha)
    return public


def main():
    result=run(os.environ.get('NOX_OWNER_REQUEST_ID',''),os.environ.get('NOX_OWNER_SOURCE_SHA',''))
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'remaining_storage_audit','data':result},separators=(',',':')),flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        code=str(exc)
        safe=code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else 'HOLD_REMAINING_STORAGE_'+type(exc).__name__.upper()
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'remaining_storage_audit_hold','data':safe}),flush=True)
        raise SystemExit(2)
