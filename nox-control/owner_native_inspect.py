#!/usr/bin/env python3
"""Six bounded read-only probes of existing NOX, without env/credential dumps."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import configparser, hashlib, json, math, os, re, shlex, shutil, stat, subprocess, time, urllib.request
ROOT = Path('/root/nox')
PROC = Path('/proc')
SECRET = re.compile(r'(?i)(?:Bearer\s+\S+|(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}|(?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*[\"\'][^\"\']{12,})')
SENSITIVE_NAME = r'(?:password|secret|api[_-]?key|access[_-]?key|authorization|(?:hf|github|gh|api|auth|access|refresh|bearer|nox)[_-]?token|token|NOX2)'
SENSITIVE_ASSIGNMENT = re.compile(r'(?i)\b'+SENSITIVE_NAME+r'[\"\']?\s*[:=]\s*(?:[\"\'][^\"\'\n]*[\"\']|[^\s,;\n]+)')
SERVICES = ('nox-train-volta-t866u', 'nox-teacher-serve-t811u',
            'nox-train-worm-t811u', 'nox-autoscale-t877u', 'nox-dispatcher-t855u',
            'nox-gpu-watchdog-t865u', 'nox-vram-guard-t829u', 'nox-priority-scheduler',
            'nox-selfheal', 'nox-distill-worm-t811u', 'nox-self-improve-t846u',
            'nox-self-learning-loop', 'nox-agent-tuner-t858u', 'nox-agent-architect-t859u',
            'nox-agent-integrator-t859u', 'nox-chat-8081', 'nox-proxy', 'nox-downloads-t802u',
            'nox-checklist-worker', 'nox-dialog-miner', 'nox-offload-t850u', 'nox-watch-swap-t845u')

def redact(value):
    value=re.sub(r'-----BEGIN [^-\n]*PRIVATE KEY-----[\s\S]*?-----END [^-\n]*PRIVATE KEY-----', '[REDACTED_PRIVATE_KEY]', value)
    value=re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', value)
    value=re.sub(r'(?i)--'+SENSITIVE_NAME+r'(?:=|\s+)(?:[\"\'][^\"\'\n]*[\"\']|[^\s,;\n]+)', '[REDACTED_ARGUMENT]',value)
    return SENSITIVE_ASSIGNMENT.sub('[REDACTED_ASSIGNMENT]', SECRET.sub('[REDACTED]',value))

def gpu_apps(output):
    rows=[]
    for line in output.splitlines()[:80]:
        cols=[x.strip() for x in line.split(',')]
        if len(cols)!=3 or not cols[0].isdigit() or not re.fullmatch(r'GPU-[A-Fa-f0-9-]+',cols[1]):continue
        rows.append({'reported_pid':int(cols[0]),'gpu_uuid':cols[1],
                     'used_mib':int(cols[2]) if cols[2].isdigit() else None})
    return rows

def map_gpu_processes(rows, apps):
    """A namespace PID match is evidence only when it identifies one local PID."""
    aliases={}
    for row in rows:
        for pid in {row['pid'], *row.get('namespace_pids',[])}:
            aliases.setdefault(pid,set()).add(row['pid'])
    by_pid={row['pid']:row for row in rows}; unresolved=[]
    for app in apps:
        candidates=aliases.get(app['reported_pid'],set())
        if len(candidates)!=1:
            unresolved.append({**app,'mapping':'UNMAPPED' if not candidates else 'AMBIGUOUS',
                               'candidate_local_pids':sorted(candidates)})
            continue
        pid=next(iter(candidates))
        by_pid[pid].setdefault('gpu_compute_apps',[]).append({**app,
            'mapping':'LOCAL_PID' if app['reported_pid']==pid else 'NSPID'})
    return unresolved

def run(args, timeout=12):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout[:100000]
    except Exception as e:
        return 99, type(e).__name__

def text(path, limit=20000):
    p = Path(path)
    if not p.is_file():
        return None
    with p.open('rb') as f:
        f.seek(max(0, p.stat().st_size-limit))
        return f.read(limit).decode(errors='replace')

def storage_mount_metadata(mountinfo=None, statvfs=None):
    """Bounded, read-only mount inventory; not a seek/write/owner-lease proof."""
    if statvfs is None:
        statvfs = os.statvfs
    if mountinfo is None:
        try:
            mountinfo = Path('/proc/self/mountinfo').read_text(encoding='utf-8')[:500000]
        except OSError:
            return {'status':'UNKNOWN_MOUNTINFO','scope':'ALLOWLISTED_ONLY','mounts':[]}
    roots = ('/', '/data', '/workspace', '/mnt', '/models', '/root/nox')
    candidates = []
    for line in mountinfo.splitlines()[:1024]:
        if ' - ' not in line:
            continue
        left, right = line.split(' - ', 1)
        fields, suffix = left.split(), right.split()
        if len(fields) < 5 or not suffix:
            continue
        mount = re.sub(r'\\([0-7]{3})', lambda m:chr(int(m.group(1),8)), fields[4])
        if mount not in roots and not any(mount.startswith(root + '/') for root in roots[1:]):
            continue
        fstype = suffix[0]
        if fstype in ('proc','sysfs','tmpfs','devtmpfs','devpts','cgroup','cgroup2','mqueue','securityfs'):
            continue
        try:
            v = statvfs(mount)
            if v.f_blocks <= 0:
                continue
            candidates.append({'path':mount,'filesystem':fstype,'total_bytes':v.f_blocks*v.f_frsize,
                               'free_bytes':v.f_bavail*v.f_frsize})
        except (OSError, ValueError):
            candidates.append({'path':mount,'filesystem':fstype,'status':'UNKNOWN_STATVFS'})
        if len(candidates) >= 24:
            break
    return {'status':'READ_ONLY_MOUNT_METADATA','scope':'ALLOWLISTED_ONLY_NOT_EXHAUSTIVE',
            'seekability':'NOT_TESTED','write_access':'NOT_TESTED','mounts':candidates}

def hardware():
    out = {}
    for label, query in (('gpu','index,uuid,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu'),('apps','pid,gpu_uuid,used_gpu_memory')):
        arg = '--query-gpu=' if label == 'gpu' else '--query-compute-apps='
        rc, s = run(['nvidia-smi', arg+query, '--format=csv,noheader,nounits'])
        out[label] = {'rc':rc, 'rows':s.splitlines()[:40]}
    out['cgroup'] = {n:text('/sys/fs/cgroup/'+n, 6000) for n in ('memory.max','memory.high','memory.current','memory.stat','memory.events','cpu.max','cpu.stat')}
    out['disk'] = {p:dict(zip(('total','used','free'),shutil.disk_usage(p))) for p in ('/root/nox','/dev/shm') if Path(p).exists()}
    out['mounts'] = storage_mount_metadata()
    out['cpu_affinity'] = len(os.sched_getaffinity(0))
    return out

def processes():
    rows = []
    gpu_rc,gpu_out=run(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_gpu_memory','--format=csv,noheader,nounits'])
    apps=gpu_apps(gpu_out) if gpu_rc==0 else []
    _,supervisor_out=run(['supervisorctl','status'])
    owners={int(m[2]):m[1] for line in supervisor_out.splitlines()
            if (m:=re.match(r'^([A-Za-z0-9_.:-]+)\s+RUNNING\s+pid\s+(\d+)',line))}
    for p in PROC.iterdir():
        if not p.name.isdigit(): continue
        try:
            argv=(p/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if not argv or not argv[0]: continue
            stat_raw=(p/'stat').read_text()
            stat=stat_raw.rsplit(') ',1)[1].split()
            if stat_raw.split(' (',1)[0] != p.name or not stat[19].isdigit():
                continue
            env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode(errors='replace').split('\0') if '=' in x)
            status=(p/'status').read_text()
            # /proc can recycle a PID between the first stat sample and the
            # slower environ/status read. Never attribute a prior nvidia-smi
            # VRAM row to a replacement process (or a disappearing task).
            post_raw=(p/'stat').read_text()
            post_stat=post_raw.rsplit(') ',1)[1].split()
            if post_raw.split(' (',1)[0] != p.name or post_stat[19] != stat[19]:
                continue
            row={'pid':int(p.name),'ppid':int(stat[1]),'state':stat[0],'starttime':stat[19], 'exe':os.path.basename(argv[0]),
                 'cuda':redact(env.get('CUDA_VISIBLE_DEVICES',''))[:150],
                 'proc_name':redact(env.get('PROC_NAME',''))[:150],
                 '_relevant':any(x in ' '.join(argv[:3]) for x in ('nox','llama','train','supervisor'))}
            row['scripts']=[redact(v) for v in argv[1:4] if v.endswith(('.py','.sh')) and len(v)<250 and '\n' not in v]
            row['args']={k:redact(argv[i+1]) for i,k in enumerate(argv[:-1]) if k in ('-m','--model','--port','-t','-np','--max-steps','--n-gpu-layers','-ngl') and len(argv[i+1])<250}
            for k in ('NSpid','VmRSS','Threads'):
                m=re.search(r'^'+k+r':\s*(.+)$',status,re.M)
                if m: row[k]=m[1]
            row['namespace_pids']=[int(x) for x in row.get('NSpid','').split() if x.isdigit()]
            rows.append(row)
        except (OSError,ValueError,IndexError): pass
    unresolved=map_gpu_processes(rows,apps)
    by_pid={row['pid']:row for row in rows}
    for row in rows:
        chain=[];pid=row['pid'];seen=set()
        for _ in range(12):
            if pid in seen or pid<2:break
            seen.add(pid)
            if pid in owners:
                row['supervisor_owner']=owners[pid];row['supervisor_pid']=pid;break
            parent=by_pid.get(pid)
            if not parent:break
            pid=parent['ppid'];chain.append(pid)
        row['ancestor_pids']=chain
    selected=[row for row in rows if row.pop('_relevant') or row.get('gpu_compute_apps')]
    selected.sort(key=lambda row:(not bool(row.get('gpu_compute_apps')),row['pid']))
    result=selected[:120]
    result.append({'record':'gpu_pid_mapping','gpu_query_rc':gpu_rc,'unresolved':unresolved,
                   'process_rows_truncated':len(selected)>120,
                   'note':'Namespace ambiguity is unresolved; CUDA_VISIBLE_DEVICES alone is not GPU ownership.'})
    return result


def hf_metadata_probe(base):
    """Bounded read-only HF metadata: never treats tensor headers as weight payload SHA."""
    out = {'record':'trainable_hf_lineage_metadata','scope':'READ_ONLY',
           'weight_payload_sha256_verified':False,'immutable_hf_revision_verified':False,
           'adapter_merge_authorized':False}
    MAX_JSON=16*1024*1024
    # The index and tensor headers do not prove a SHA256 of the weight payload.
    DTYPE_BYTES = {
        'BOOL': 1, 'U8': 1, 'I8': 1, 'F8_E4M3': 1, 'F8_E5M2': 1, 'F8_E8M0': 1,
        'U16': 2, 'I16': 2, 'F16': 2, 'BF16': 2,
        'U32': 4, 'I32': 4, 'F32': 4, 'U64': 8, 'I64': 8, 'F64': 8,
    }
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:raise ValueError('DUPLICATE_JSON_KEY')
            obj[key]=value
        return obj
    try:
        files={}
        for name in ('tokenizer.json','tokenizer_config.json','special_tokens_map.json',
                     'added_tokens.json','chat_template.jinja','generation_config.json'):
            p=base/name
            if not p.exists():continue
            if p.is_symlink() or not p.is_file() or p.stat().st_size>32*1024*1024:
                raise ValueError('HOLD_TOKENIZER_FILE_UNSAFE')
            h=hashlib.sha256()
            with p.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
            files[name]={'sha256':h.hexdigest(),'bytes':p.stat().st_size}
        out['tokenizer_file_digests']=files
        if 'tokenizer.json' not in files or 'tokenizer_config.json' not in files:
            raise ValueError('HOLD_TOKENIZER_REQUIRED_FILES')
        idx=base/'model.safetensors.index.json'
        if idx.is_symlink() or not idx.is_file() or idx.stat().st_size>MAX_JSON:
            raise ValueError('HOLD_SHARD_INDEX_MISSING_OR_UNSAFE')
        idxbytes=idx.read_bytes(); index=json.loads(idxbytes,object_pairs_hook=unique)
        mapping=index.get('weight_map')
        if not isinstance(mapping,dict) or not mapping or len(mapping)>100000:
            raise ValueError('HOLD_SHARD_INDEX_MAP')
        names=set(mapping.values())
        if any(not isinstance(k,str) or not k or not isinstance(v,str) or
               not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.safetensors',v)
               for k,v in mapping.items()):
            raise ValueError('HOLD_SHARD_NAME_UNSAFE')
        actual={p.name for p in base.glob('*.safetensors')}
        if actual!=names or len(names)>50:
            raise ValueError('HOLD_SHARD_INDEX_FILESET_MISMATCH')
        tensors=[]; total_bytes=0
        for name in sorted(names):
            p=base/name
            if p.is_symlink() or not p.is_file():raise ValueError('HOLD_SHARD_UNSAFE')
            nbytes=p.stat().st_size;total_bytes+=nbytes
            with p.open('rb') as stream:
                n=int.from_bytes(stream.read(8),'little')
                if not 2<=n<=MAX_JSON or nbytes<8+n:
                    raise ValueError('HOLD_SAFETENSORS_HEADER_SIZE')
                header=json.loads(stream.read(n),object_pairs_hook=unique)
            if not isinstance(header,dict) or len(header)>100000:
                raise ValueError('HOLD_SAFETENSORS_HEADER_OBJECT')
            payload_bytes=nbytes-8-n
            ranges=[]
            entries=[(k,v) for k,v in header.items() if k!='__metadata__']
            from_index={k for k,v in mapping.items() if v==name}
            if {k for k,_ in entries}!=from_index:
                raise ValueError('HOLD_TENSOR_INDEX_HEADER_MISMATCH')
            for key,desc in entries:
                if not isinstance(desc,dict):raise ValueError('HOLD_TENSOR_DESCRIPTOR')
                shape=desc.get('shape'); dtype=desc.get('dtype');offsets=desc.get('data_offsets')
                if (not isinstance(shape,list) or len(shape)>16 or
                    any(type(v)!=int or v<0 for v in shape) or
                    not isinstance(dtype,str) or not re.fullmatch(r'[A-Z0-9_]{2,16}',dtype) or
                    not isinstance(offsets,list) or len(offsets)!=2 or
                    any(type(v)!=int or v<0 for v in offsets) or
                    offsets[0]>offsets[1] or offsets[1]>nbytes-8-n):
                    raise ValueError('HOLD_TENSOR_HEADER_INVALID')
                width=DTYPE_BYTES.get(dtype)
                if width is None:
                    raise ValueError('HOLD_TENSOR_DTYPE_UNSUPPORTED')
                if offsets[1]-offsets[0] != math.prod(shape)*width:
                    raise ValueError('HOLD_TENSOR_BYTE_SIZE')
                ranges.append((offsets[0],offsets[1]))
                tensors.append((key,name,dtype,shape))
            cursor=0
            for first,last in sorted(ranges):
                if first!=cursor:
                    raise ValueError('HOLD_TENSOR_LAYOUT')
                cursor=last
            if cursor!=payload_bytes:
                raise ValueError('HOLD_TENSOR_LAYOUT')
        out['shard_index_sha256']=hashlib.sha256(idxbytes).hexdigest()
        out['tensor_metadata_sha256']=hashlib.sha256(json.dumps(
            sorted(tensors),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        out['tensor_count']=len(tensors);out['shards_count']=len(names)
        out['shards_total_bytes']=total_bytes
        out['status']='HEADER_INDEX_MATCH_ONLY_CONTENT_SHA_PENDING'
    except (OSError,UnicodeError,ValueError,TypeError,OverflowError) as e:
        code=str(e)
        out['status']=code if code.startswith('HOLD_') else 'HOLD_METADATA_'+type(e).__name__.upper()
    return out

def training():
    rows=[]
    keys={'phase','step','global_step','loss','smoke','rows','ts','updated_msk','program','error','method','model','s_per_step','eta_sec','best_gated','max_steps','trainable_params','resume'}
    for name in ('train_volta_t866u.json','train_volta_wrapper_t866u.json','train_heartbeat_t811u.json'):
        p=ROOT/'status'/name; s=text(p)
        try:
            d=json.loads(s or '{}');clean={k:d[k] for k in keys if k in d}
            rows.append({'path':str(p),'mtime':p.stat().st_mtime if p.exists() else None,'data':clean})
        except ValueError: rows.append({'path':str(p),'parse_error':True})
    for name in ('TRAIN_HOLD.flag','train_wants_gpu1','train_volta_t866u.attempts','train_cpu_max.env'):
        s=text(ROOT/'state'/name,1200)
        rows.append({'flag':name,'value':SECRET.sub('[REDACTED]',s) if s is not None else None})
    for name in ('train_volta_t866u.log','train_volta_t866u.supervisor.err'):
        s=text(ROOT/'logs'/name,15000) or ''
        lines=[SECRET.sub('[REDACTED]',x)[:900] for x in s.splitlines() if re.search(r'FAIL|Error|Traceback|step|loss|load 4bit|budget|dispatch|phase|giving up|no safe|HOLD',x)]
        rows.append({'log':name,'tail':lines[-18:]})
    for base in (ROOT/'lora'/'qlora_t866u',ROOT/'lora'/'qlora_t811u'):
        for p in base.glob('runs*/checkpoint-*/trainer_state.json'):
            s=text(p,300000)
            try:
                d=json.loads(s or '{}'); rows.append({'checkpoint':str(p.parent),'global_step':d.get('global_step'),'mtime':p.stat().st_mtime})
            except ValueError: pass
            if len(rows)>45: break
    rc,out=run(['supervisorctl','status'])
    rows.append({'supervisor_rc':rc,'services':[x for x in out.splitlines() if re.match(r'^nox[-_\w]*\s+(RUNNING|STARTING|STOPPED|FATAL|BACKOFF|EXITED|STOPPING)',x)][:80]})
    base=ROOT/'progress_pull_t784u/workspace-2-2/nox36/ckpt/final/merged_hf'
    config=base/'config.json'
    if config.is_file() and not config.is_symlink() and config.stat().st_size<100000:
        try:
            data=config.read_bytes();d=json.loads(data)
            allowed=('model_type','architectures','hidden_size','intermediate_size','num_hidden_layers',
                     'num_attention_heads','num_key_value_heads','vocab_size','num_experts','num_local_experts',
                     'num_experts_per_tok','decoder_sparse_step','torch_dtype','dtype','num_parameters','tie_word_embeddings')
            rows.append({'record':'trainable_hf_base','path':str(base),'config_sha256':hashlib.sha256(data).hexdigest(),
                         'config':{k:d[k] for k in allowed if k in d},
                         'weight_files':[{'name':p.name,'bytes':p.stat().st_size}
                                         for p in sorted(base.glob('*.safetensors'))[:50] if p.is_file() and not p.is_symlink()]})
        except (OSError,ValueError,TypeError):rows.append({'record':'trainable_hf_base','metadata_error':True})
    rows.append(hf_metadata_probe(base))
    rows.extend(qwen_training_readback())
    return rows

def qwen_training_readback():
    """Read bounded receipts of the EXISTING Qwen student; never infer updates.

    No corpus text, optimizer tensors, arbitrary logs or other model paths are
    opened. A Supervisor EXITED/FATAL line is not a terminal-result receipt.
    """
    base=ROOT/'lora'/'qwen35_9b'
    if base.is_symlink() or not base.is_dir():
        return [{'record':'qwen35_student','state':'RUN_DIRECTORY_NOT_OBSERVED'}]
    runs=[p for p in base.glob('[0-9]*') if p.is_dir() and not p.is_symlink()]
    rows=[]
    for directory in sorted(runs)[-3:]:
        for name in ('owner_progress.json','owner_last_result.json','owner_acceptance.json'):
            path=directory/name
            row={'record':'qwen35_student','run':directory.name,'receipt':name}
            if path.is_symlink() or not path.is_file():
                row['state']='NOT_OBSERVED';rows.append(row);continue
            try:
                st=path.stat()
                if st.st_size>200000:
                    row['state']='SIZE_HOLD';rows.append(row);continue
                # No optimizer counter may come from an ambiguous or torn receipt.
                # Python json.loads otherwise accepts duplicate keys and NaN/Infinity.
                with path.open('rb') as stream:
                    raw=stream.read(200001)
                after=path.stat()
                if (len(raw)!=st.st_size or len(raw)>200000 or
                    (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)!=
                    (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):
                    raise ValueError('QWEN_RECEIPT_CHANGED_DURING_READ')
                def reject_duplicate_keys(pairs):
                    unique={}
                    for key,value in pairs:
                        if key in unique:raise ValueError('QWEN_RECEIPT_DUPLICATE_FIELD')
                        unique[key]=value
                    return unique
                def reject_nonfinite(_):
                    raise ValueError('QWEN_RECEIPT_NONFINITE_JSON')
                row.update(bytes=len(raw),mtime=st.st_mtime,sha256=hashlib.sha256(raw).hexdigest())
                data=json.loads(raw,object_pairs_hook=reject_duplicate_keys,
                                parse_constant=reject_nonfinite)
                if not isinstance(data,dict):
                    row['state']='UNEXPECTED_FORMAT';rows.append(row);continue
                # Receipt text is owner-private and counters are not independent proof.
                row.update(state='METADATA_READ_ONLY',scope='SELF_REPORTED_NOT_LIVE_PROOF',
                           fields=safe_qwen_receipt_fields(data))
            except (OSError,ValueError,TypeError):
                row['state']='READ_OR_PARSE_HOLD'
            rows.append(row)
    if not rows:return [{'record':'qwen35_student','state':'NO_RUN_RECEIPTS_OBSERVED'}]
    return rows

def supervisor_config():
    """Read known NOX configuration files, never environment/credentials sections."""
    directory=Path('/etc/supervisor/conf.d')
    names={'nox.conf','nox-runtime.conf'}
    for service in SERVICES:
        names.update((service+'.conf',service.replace('-','_')+'.conf'))
    fields=('command','directory','autostart','autorestart','startsecs','startretries',
            'stopsignal','stopwaitsecs','stopasgroup','killasgroup','priority')
    rows=[]
    for name in sorted(names):
        p=directory/name
        if not p.is_file() or p.is_symlink() or p.stat().st_size>250000:continue
        parser=configparser.ConfigParser(interpolation=None,strict=False)
        try:parser.read(p)
        except (OSError,configparser.Error):continue
        for service in SERVICES:
            section='program:'+service
            if not parser.has_section(section):continue
            selected={key:redact(parser.get(section,key))[:1800] for key in fields if parser.has_option(section,key)}
            rows.append({'path':str(p),'service':service,'settings':selected})
    return rows

SFTCONFIG_REQUIRED = (
    'output_dir', 'per_device_train_batch_size', 'gradient_accumulation_steps',
    'max_length', 'max_steps', 'fp16', 'bf16', 'packing',
    'gradient_checkpointing', 'gradient_checkpointing_kwargs',
    'dataloader_num_workers', 'logging_steps', 'save_steps',
    'save_total_limit', 'warmup_steps', 'learning_rate', 'optim',
    'lr_scheduler_type', 'report_to',
)


def parse_sftconfig_signature_probe(rc, output):
    """Fail closed on the installed TRL signature; never report training."""
    result = {'record': 'pinned_trl_sftconfig_signature',
              'scope': 'READ_ONLY_SIGNATURE_NO_TRAINER',
              'constructor_executed': False, 'optimizer_updates': 0}
    if rc != 0:
        return dict(result, status='HOLD_NATIVE_TRL_SIGNATURE_IMPORT')
    matches = [line[len('NOX_SFTCONFIG_SIGNATURE='):]
               for line in output.splitlines()
               if line.startswith('NOX_SFTCONFIG_SIGNATURE=')]
    if len(matches) != 1 or len(matches[0]) > 4096:
        return dict(result, status='HOLD_NATIVE_TRL_SIGNATURE_OUTPUT')
    try:
        # GitHub/owner-native receipts are evidence, not trusted constructor
        # capabilities. Duplicate keys can silently replace a safe capability
        # with its opposite in Python's permissive json.loads().
        def reject_duplicate_fields(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError('SFTCONFIG_DUPLICATE_SIGNATURE_FIELD')
                out[key] = value
            return out
        def reject_nonfinite(_value):
            raise ValueError('SFTCONFIG_NONFINITE_SIGNATURE_FIELD')
        data = json.loads(matches[0], object_pairs_hook=reject_duplicate_fields,
                          parse_constant=reject_nonfinite)
        if (not isinstance(data, dict) or
                set(data) != {'schema', 'trl_version', 'missing_required_kwargs',
                              'save_safetensors_parameter'} or
                data.get('schema') != 'NOX_SFTCONFIG_NATIVE_SIGNATURE_V1' or
                type(data.get('trl_version')) is not str or
                not re.fullmatch(r'[0-9A-Za-z.+_-]{1,64}', data['trl_version']) or
                type(data.get('save_safetensors_parameter')) is not bool or
                not isinstance(data.get('missing_required_kwargs'), list) or
                len(set(map(str, data['missing_required_kwargs']))) != len(data['missing_required_kwargs']) or
                any(type(k) is not str or k not in SFTCONFIG_REQUIRED
                    for k in data['missing_required_kwargs'])):
            raise ValueError('INVALID_SIGNATURE_RECORD')
    except (ValueError, TypeError, UnicodeError):
        return dict(result, status='HOLD_NATIVE_TRL_SIGNATURE_SCHEMA')
    result.update(trl_version=data['trl_version'],
                  save_safetensors_parameter=data['save_safetensors_parameter'],
                  missing_required_kwargs=data['missing_required_kwargs'])
    if data['missing_required_kwargs']:
        result['status'] = 'HOLD_REQUIRED_SFTCONFIG_KWARGS_UNSUPPORTED'
    elif data['save_safetensors_parameter']:
        result['status'] = 'SIGNATURE_ACCEPTS_LEGACY_SAVE_SAFETENSORS'
    else:
        result['status'] = 'LEGACY_TRUE_REQUIRES_SAFE_OMISSION'
    return result


def pinned_python_path_status(py, venv_root=Path('/root/venv_volta'),
                              trusted_uid=0,
                              system_dirs=(Path('/usr/bin'), Path('/usr/local/bin'))):
    """Validate a pinned venv Python, including normal root-owned venv symlinks.

    Only the known venv path and root-controlled executable targets are allowed.
    Do not run a path that escaped into a writable directory. This is a
    read-only metadata gate, not a writer lease or a CUDA/ABI acceptance.
    """
    if py != venv_root / 'bin' / 'python':
        return 'HOLD_PINNED_NATIVE_PYTHON_PATH'
    try:
        for directory in (venv_root, venv_root / 'bin'):
            metadata = directory.lstat()
            if (not stat.S_ISDIR(metadata.st_mode) or
                    metadata.st_uid != trusted_uid or metadata.st_mode & 0o022):
                return 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'
        config = venv_root / 'pyvenv.cfg'
        config_stat = config.lstat()
        if (not stat.S_ISREG(config_stat.st_mode) or
                config_stat.st_uid != trusted_uid or
                config_stat.st_mode & 0o022 or
                config_stat.st_size > 65536):
            return 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'
        entry_stat = py.lstat()
        if (entry_stat.st_uid != trusted_uid or
                not (stat.S_ISLNK(entry_stat.st_mode) or
                     stat.S_ISREG(entry_stat.st_mode))):
            return 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'
        resolved = py.resolve(strict=True)
        target_stat = resolved.stat()
        approved_local = (
            resolved.parent == venv_root / 'bin' and
            re.fullmatch(r'python(?:3(?:\.[0-9]{1,2})?)?', resolved.name) is not None)
        approved_system = (
            resolved.parent in system_dirs and
            re.fullmatch(r'python3(?:\.[0-9]{1,2})?', resolved.name) is not None)
        if (not (approved_local or approved_system) or
                not stat.S_ISREG(target_stat.st_mode) or
                not target_stat.st_mode & 0o111 or
                target_stat.st_uid != trusted_uid or
                target_stat.st_mode & 0o022):
            return 'HOLD_PINNED_NATIVE_PYTHON_UNTRUSTED'
    except (OSError, RuntimeError):
        return 'HOLD_PINNED_NATIVE_PYTHON_MISSING'
    return 'PINNED_NATIVE_PYTHON_TRUSTED'


def pinned_sftconfig_signature_probe(py):
    """Inspect the vetted venv interpreter, not its symlink spelling."""
    admission = pinned_python_path_status(py)
    if admission != 'PINNED_NATIVE_PYTHON_TRUSTED':
        return {'record': 'pinned_trl_sftconfig_signature',
                'scope': 'READ_ONLY_SIGNATURE_NO_TRAINER',
                'status': admission,
                'constructor_executed': False, 'optimizer_updates': 0}
    # Constructing SFTConfig() may initialise devices; inspect only its real
    # installed signature. A passed signature is not a live training test.
    code = """
import inspect, importlib.metadata, json, os, sys
if sys.version_info[:2] != (3, 12) or os.path.realpath(sys.prefix) != '/root/venv_volta':
    raise RuntimeError('PINNED_VENV_INTERPRETER_IDENTITY_HOLD')
from trl import SFTConfig
required = %r
parameters = inspect.signature(SFTConfig).parameters
accepted = {key for key, value in parameters.items()
            if value.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                              inspect.Parameter.KEYWORD_ONLY)}
print('NOX_SFTCONFIG_SIGNATURE=' + json.dumps({
  'schema': 'NOX_SFTCONFIG_NATIVE_SIGNATURE_V1',
  'trl_version': importlib.metadata.version('trl'),
  'missing_required_kwargs': [key for key in required if key not in accepted],
  'save_safetensors_parameter': 'save_safetensors' in accepted,
}, separators=(',', ':')))
""" % (SFTCONFIG_REQUIRED,)
    rc, output = run([str(py), '-I', '-c', code], timeout=30)
    return parse_sftconfig_signature_probe(rc, output)



def installed_package_versions_readback(py):
    """Inspect metadata only in a trusted, isolated pinned venv; never import torch."""
    status = pinned_python_path_status(py)
    result = {'record': 'installed_package_versions', 'python': str(py),
              'status': status, 'rc': None, 'versions': {},
              'cuda_context_created': False, 'trainer_started': False}
    if status != 'PINNED_NATIVE_PYTHON_TRUSTED':
        return result
    # The child checks actual version and sys.prefix, not only symlink ownership.
    code = """
import importlib.metadata as m, json, os, sys
if sys.version_info[:2] != (3, 12) or os.path.realpath(sys.prefix) != '/root/venv_volta':
    raise SystemExit('HOLD_PINNED_VENV_RUNTIME_IDENTITY')
names = ['torch','transformers','accelerate','datasets','safetensors','peft',
         'bitsandbytes','trl','deepspeed','psutil','nvidia-ml-py','sqlite-vec',
         'playwright','pytest','ruff']
versions = {}
for name in names:
    try:
        versions[name] = m.version(name)
    except m.PackageNotFoundError:
        versions[name] = None
print(json.dumps(versions, separators=(',', ':')))
"""
    rc, output = run([str(py), '-I', '-c', code], timeout=20)
    result['rc'] = rc
    if rc != 0 or len(output) > 16384:
        result['status'] = 'HOLD_PACKAGE_METADATA_PROBE_FAILED'
        return result
    try:
        versions = json.loads(output)
    except (TypeError, ValueError):
        result['status'] = 'HOLD_PACKAGE_METADATA_INVALID'
        return result
    names = ('torch','transformers','accelerate','datasets','safetensors',
             'peft','bitsandbytes','trl','deepspeed','psutil','nvidia-ml-py',
             'sqlite-vec','playwright','pytest','ruff')
    if (not isinstance(versions, dict) or set(versions) != set(names) or
            any(v is not None and
                (not isinstance(v, str) or len(v) > 128 or
                 not re.fullmatch(r'[0-9A-Za-z.+_!\\-]+', v))
                for v in versions.values())):
        result['status'] = 'HOLD_PACKAGE_METADATA_INVALID'
        return result
    result['status'] = 'READ_ONLY_VERSION_METADATA'
    result['versions'] = versions
    return result


def controls():
    configs=supervisor_config()
    names=['train_qlora_35b_t866u.py','run_train_volta_t866u.sh',
           'nox_autoscale_t877u.py','owner_dispatcher_mentor.py','nox_dispatcher_t855u.py',
           'teacher_serve_t811u.sh','vram_guard_t829u.py','gpu_hang_watchdog_t865u.py']
    # Only exact training-service script references inside the known scripts root.
    for config in configs:
        if config['service']!='nox-train-volta-t866u':continue
        try:args=shlex.split(config['settings'].get('command',''))
        except ValueError:continue
        for arg in args:
            p=Path(arg)
            if p.parent==ROOT/'scripts' and re.fullmatch(r'[A-Za-z0-9_]*t866u\.(py|sh)',p.name) and p.name not in names:names.append(p.name)
    rows=[];remaining=130000
    for name in names:
        p=ROOT/'scripts'/name
        if not p.is_file() or p.is_symlink(): continue
        if p.stat().st_size>250000:
            rows.append({'path':str(p),'source_omitted':'SIZE_LIMIT'});continue
        b=p.read_bytes(); row={'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
        s=b.decode(errors='replace')
        safe=redact(s);row['source_redacted']=safe!=s
        if len(safe.encode())<=remaining:
            row['source']=safe;remaining-=len(safe.encode())
        else:
            lines=s.splitlines(); indexes=set()
            for i,line in enumerate(lines):
                if re.search(r'train_wants_gpu1|nox-train-volta|TRAIN_HOLD|TRAIN_PAUSE_REQUEST|supervisorctl|train_qlora|SIGKILL|SIGSTOP|def h_start_qlora|def h_ensure_program|def _start_gpu1_teachers|def resume_svc',line): indexes.update(range(max(0,i-4),min(len(lines),i+7)))
            excerpts='\n'.join(f'{i+1}: '+redact(lines[i]) for i in sorted(indexes))
            excerpts=excerpts.encode()[:max(0,remaining)].decode(errors='ignore')
            row['excerpts']=excerpts.splitlines();row['source_truncated']=True;remaining-=len(excerpts.encode())
        rows.append(row)
    rows.append({'record':'supervisor_configuration','services':configs})
    extra=(Path('/root/nox_selfheal.py'),ROOT/'scripts/nox_priority_scheduler.py',
           ROOT/'scripts/download_t802u.sh',ROOT/'scripts/chat_proxy.py',
           ROOT/'scripts/nox_agent_architect_t859u.py',ROOT/'scripts/nox_agent_integrator_t859u.py',
           ROOT/'scripts/nox_agent_tuner_t858u.py')
    for p in extra:
        if not p.is_file() or p.is_symlink() or p.stat().st_size>110000:continue
        body=p.read_bytes();source=body.decode(errors='replace');safe=redact(source)
        rows.append({'record':'extension_source','path':str(p),'sha256':hashlib.sha256(body).hexdigest(),
                     'bytes':len(body),'source_redacted':safe!=source,'source':safe})
    # Inventory package metadata only through the pinned interpreter fence.
    # A symlink's is_file() is NOT authorization to execute it.
    py=Path('/root/venv_volta/bin/python')
    rows.append(installed_package_versions_readback(py))
    rows.append(pinned_sftconfig_signature_probe(py))
    # Only filenames and selected nonsecret routing fields, never credentials.
    routes=[]
    for p in sorted((ROOT/'config').glob('*.json'))[:120]:
        if p.is_symlink() or not p.is_file() or p.stat().st_size>250000:continue
        if not re.search(r'teacher|mentor|council|provider|brain|architect|integrator|download',p.name,re.I):continue
        try:d=json.loads(p.read_text())
        except (OSError,ValueError):continue
        fields={}
        def select(obj,prefix='',depth=0):
            if depth>5:return
            if isinstance(obj,dict):
                for key,value in obj.items():
                    if re.search(SENSITIVE_NAME,str(key),re.I):continue
                    label=(prefix+'.'+str(key)).strip('.')
                    if isinstance(value,(dict,list)):select(value,label,depth+1)
                    elif re.fullmatch(r'enabled|model|model_id|provider|base_url|endpoint|port|role',str(key),re.I):
                        fields[label]=redact(str(value)).split('?',1)[0][:350]
            elif isinstance(obj,list):
                for i,value in enumerate(obj[:20]):select(value,prefix+'.'+str(i),depth+1)
        select(d);routes.append({'path':str(p),'routing':fields})
    rows.append({'record':'model_routing_configuration','files':routes})
    inventory=[]
    for directory in (ROOT/'models',ROOT/'models/teachers',ROOT/'models/judge',ROOT/'lora/qlora_t866u'):
        if not directory.is_dir():continue
        for p in sorted(directory.iterdir())[:100]:
            if p.is_file():
                inventory.append({'path':str(p),'bytes':p.stat().st_size,'symlink':p.is_symlink(),
                                  'target':str(p.resolve()) if p.is_symlink() else None})
    rows.append({'record':'model_file_inventory','files':inventory})
    pool=ROOT/'config/dispatcher_agents_t868u.json'
    if pool.is_file() and not pool.is_symlink() and pool.stat().st_size<100000:
        body=pool.read_bytes()
        # The worker configuration is operational data. Never emit credential fields.
        try:
            data=json.loads(body)
            def clean(value):
                if isinstance(value,dict):
                    return {key:clean(item) for key,item in value.items()
                            if not re.search(SENSITIVE_NAME,str(key),re.I)}
                if isinstance(value,list):return [clean(item) for item in value[:120]]
                if isinstance(value,str):return redact(value)[:1500]
                return value
            rows.append({'record':'dispatcher_workers','path':str(pool),
                         'sha256':hashlib.sha256(body).hexdigest(),'configuration':clean(data)})
        except (ValueError,TypeError):
            rows.append({'record':'dispatcher_workers','parse_error':True})
    for name in ('sft_trainer.py','utils.py'):
        for p in sorted(Path('/root/venv_volta/lib').glob('python3.*/site-packages/trl/trainer/'+name))[:1]:
            if not p.is_file() or p.is_symlink() or p.stat().st_size>1000000:continue
            b=p.read_bytes();lines=b.decode(errors='replace').splitlines();indexes=set()
            for i,line in enumerate(lines):
                if re.search(r'bf16|bfloat16|peft_module_casting',line):indexes.update(range(max(0,i-6),min(len(lines),i+8)))
            excerpts=[f'{i+1}: '+redact(lines[i]) for i in sorted(indexes)][:120]
            rows.append({'record':'installed_trl_dtype_source','path':str(p),'sha256':hashlib.sha256(b).hexdigest(),
                         'excerpts':'\n'.join(excerpts)[:12000]})
    return rows

def memory_metadata_inventory(roots):
    """Bounded nonsecret metadata for DB filenames, never a recall/health PASS.

    Do not follow symlinks, recurse into training data or read private rows.
    Canonical /root/nox/kb/knowledge.sqlite was missed by the older *.db glob.
    """
    files=[];seen=set()
    for root in roots:
        if root.is_symlink() or not root.is_dir(): continue
        # Sort candidate names together before inode deduplication: per-extension
        # traversal once kept c_alias.sqlite instead of canonical c.sqlite3.
        # Preserve the existing 50-per-extension and 100-total bounds.
        candidates=set()
        for pattern in ('*.db','*.sqlite','*.sqlite3'):
            candidates.update(sorted(root.glob(pattern))[:50])
        for p in sorted(candidates):
            if p.is_symlink() or not p.is_file(): continue
            try: st=p.stat()
            except OSError: continue
            key=(st.st_dev,st.st_ino)
            if key in seen: continue
            seen.add(key)
            files.append({'path':str(p),'bytes':st.st_size,'mtime':st.st_mtime})
            if len(files)>=100: return files
    return files

def chat_storage():
    out={'health':{},'storage':{}}
    for port in (8080,8081,8082):
        t=time.monotonic()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=5) as r: code=r.status
        except Exception as e: code=type(e).__name__
        out['health'][str(port)]={'status':code,'seconds':round(time.monotonic()-t,3)}
    if shutil.which('rclone'):
        rc,s=run(['rclone','listremotes']);out['storage']={'rclone':True,'rc':rc,'remotes':[x for x in s.splitlines() if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}:',x)]}
    else: out['storage']={'rclone':False}
    # Filesystem inventory is NOT a successful owner S03 recall. The canonical
    # original S03 often uses knowledge.sqlite, rather than a *.db suffix.
    out['memory_files']=memory_metadata_inventory((ROOT/'memory',ROOT/'kb'))
    out['memory_files_scope']='LOCAL_METADATA_ONLY'
    out['s03_recall_status']='UNKNOWN_NOT_PROBED'
    out['model_slots_scope']='INFERENCE_CONTEXT_SLOTS_NOT_MODEL_INSTANCES'
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as response:
            slots=json.loads(response.read(100000))
        out['model_slots']=[{key:slot[key] for key in ('id','is_processing','state','n_ctx') if key in slot}
                            for slot in slots if isinstance(slot,dict)] if isinstance(slots,list) else None
    except Exception as exc:out['model_slots_error']=type(exc).__name__
    return out


# Native maintenance receipts and queue task.result may hold owner-private text.
# Print only bounded, validated status metadata (not raw JSON or messages).
PUBLIC_STATUS_CODE = re.compile(r'^[A-Za-z][A-Za-z0-9_:-]{0,95}$')
PUBLIC_TASK_ID = re.compile(r'^owner\.[A-Za-z0-9_.:-]{1,95}$')
PUBLIC_EVIDENCE_NUMBERS = frozenset((
    'successful_optimizer_steps', 'attempted_steps', 'skipped_steps',
    'verified_files', 'verified_bytes', 'training_started',
    'optimizer_steps_verified', 'native_verified', 'source_sha_verified'))

def safe_qwen_receipt_fields(data):
    """Only public coded statuses/finite scalar metrics from a self-reported receipt."""
    if not isinstance(data, dict):
        return {}
    fields = {}
    for key in ('schema', 'state', 'status', 'phase', 'error', 'reason'):
        value = data.get(key)
        if type(value) is str and PUBLIC_STATUS_CODE.fullmatch(value):
            fields[key] = value
    request = data.get('request')
    if type(request) is str and re.fullmatch(r'[0-9]{1,24}', request):
        fields['request'] = request
    for key in ('training_started', 'optimizer_steps_verified', 'checkpoint_verified'):
        value = data.get(key)
        if type(value) is bool:
            fields[key] = value
    for key in ('successful_optimizer_steps', 'successful_updates', 'global_step', 'step'):
        value = data.get(key)
        if type(value) is int and 0 <= value <= 10**12:
            fields[key] = value
    value = data.get('loss')
    if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**6:
        fields['loss'] = value
    for key in ('finished_at', 'updated_at'):
        value = data.get(key)
        if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**12:
            fields[key] = value
    return fields


def bounded_receipt_meta(path, limit=100000):
    """Read-only file identity plus approved status codes; never export raw payload."""
    path = Path(path)
    try:
        if any(p.is_symlink() for p in (path, *path.parents)):
            return {'state': 'HOLD_SYMLINK'}
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                return {'state': 'HOLD_FILE_BOUND'}
            raw = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            stamp = lambda st: (st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size)
            if len(raw) > limit or len(raw) != before.st_size or stamp(before) != stamp(after):
                return {'state': 'HOLD_FILE_CHANGED'}
        def no_duplicates(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate JSON key')
                result[key] = value
            return result
        try:
            obj = json.loads(raw, object_pairs_hook=no_duplicates,
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        except (ValueError, UnicodeDecodeError, TypeError):
            return {'state': 'HOLD_INVALID_JSON'}
        if not isinstance(obj, dict):
            return {'state': 'HOLD_INVALID_OBJECT'}
        fields = {}
        for key in ('schema', 'state', 'status', 'kind', 'result_state'):
            value = obj.get(key)
            if isinstance(value, str) and PUBLIC_STATUS_CODE.fullmatch(value):
                fields[key] = value
        for key in PUBLIC_EVIDENCE_NUMBERS:
            value = obj.get(key)
            if type(value) is bool or (type(value) is int and 0 <= value <= 10 ** 15):
                fields[key] = value
        return {'state': 'READ_ONLY_METADATA', 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'fields': fields}
    except (OSError, ValueError):
        return {'state': 'HOLD_READ_FAILED'}


def safe_owner_task(task):
    """A task result may contain private conversation content; withhold it."""
    if not isinstance(task, dict):
        return {'state': 'HOLD_INVALID_TASK'}
    fields = {}
    task_id = task.get('id')
    if isinstance(task_id, str) and PUBLIC_TASK_ID.fullmatch(task_id):
        fields['id'] = task_id
    for key in ('status', 'result_state'):
        value = task.get(key)
        if isinstance(value, str) and PUBLIC_STATUS_CODE.fullmatch(value):
            fields[key] = value
    for key in ('retries', 'finished_at', 'owner_claim_epoch'):
        value = task.get(key)
        if type(value) is int and 0 <= value <= 10 ** 15:
            fields[key] = value
    fields['result_payload_withheld'] = 'result' in task
    return fields


def receipts():
    rows = []
    for p in sorted((ROOT / 'state').glob('owner_maintenance_*.json'))[-8:]:
        rows.append({'path': str(p), 'evidence': bounded_receipt_meta(p)})
    return rows


def owner_component_readback():
    rows = []
    for name in ('owner.training_stack', 'owner.dispatcher', 'owner.chat',
                 'owner.memory', 'owner.storage', 'owner.downloads'):
        p = ROOT / 'state/owner_components' / (name + '.json')
        if p.exists() or p.is_symlink():
            rows.append({'component': name, 'evidence': bounded_receipt_meta(p)})
    queue = ROOT / 'state/dispatcher/state.json'
    tasks = []
    queue_scope = 'HOLD_NOT_READ'
    if queue.is_file() and not queue.is_symlink() and queue.stat().st_size < 3000000:
        try:
            with queue.open('rb') as stream:
                raw = stream.read(3000001)
            state = json.loads(raw)
            if isinstance(state, dict) and isinstance(state.get('tasks'), dict):
                tasks = [safe_owner_task(dict(task, id=task.get('id', name)))
                         for name, task in state['tasks'].items()
                         if isinstance(name, str) and name.startswith('owner.')
                         and isinstance(task, dict)][:512]
                queue_scope = 'OWNER_TASK_STATUS_ONLY_NO_RESULTS'
        except (OSError, ValueError, TypeError):
            queue_scope = 'HOLD_INVALID_QUEUE'
    print('NOX_MAINT_COMPONENTS=' + json.dumps(
        {'receipts': rows, 'tasks': tasks, 'queue_scope': queue_scope},
        separators=(',', ':'), allow_nan=False), flush=True)

def bounded_capacity_readback():
    probe=ROOT/'scripts/owner_capacity_probe.py'
    expected='7ce19fe09a2af1571efc9e3c43751f8243d3cba7e7c60678053b334cede70d31'
    if not probe.is_file() or probe.is_symlink() or hashlib.sha256(probe.read_bytes()).hexdigest()!=expected:
        print('NOX_MAINT_CAPACITY_HOLD=PINNED_NATIVE_PROBE_MISSING',flush=True);return
    # Public short fixtures only; existing probe checks idle chat, native BOOST
    # state and cgroup pressure before admitting any model work.
    p=subprocess.run(['python3',str(probe),'--mode','TASK_BOOST','--samples','6',
                      '--reserve-slots','0','--deadline-sec','90'],capture_output=True,text=True,timeout=115)
    for line in p.stdout.splitlines():
        if line.startswith('NOX_MAINT_CAPACITY') and len(line)<150000:print(line,flush=True)

def owner_safety_snapshot():
    """Read-only owner/8081 admission evidence; NEVER interpret a flag absence as a lease."""
    root = ROOT
    stop_names = ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
                  'state/STOP', 'state/STOP.flag')
    paths = [root / name for name in stop_names] + [Path('/workspace/NOX_STOP'),
                                                    root / 'state/TRAIN_HOLD.flag',
                                                    root / 'state/TRAIN_PAUSE_REQUEST.flag']
    def kind(path):
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                return 'HOLD_SYMLINK'
            return 'PRESENT' if stat.S_ISREG(mode) else 'HOLD_NONREGULAR'
        except FileNotFoundError:
            return 'ABSENT'
        except OSError:
            return 'UNKNOWN'
    flags = {str(path): kind(path) for path in paths}
    # Include every canonical STOP alias (including /state/STOP.flag),
    # and the independent /workspace/NOX_STOP path; training flags follow.
    manual_flags = [flags[str(p)] for p in paths[:len(stop_names) + 1]]
    owner_stop = ('PRESENT' if 'PRESENT' in manual_flags
                  else 'HOLD_UNSAFE_FLAG' if any(x != 'ABSENT' for x in manual_flags)
                  else 'NOT_OBSERVED_NOT_AUTHORIZATION')
    maintenance_lock = kind(root / 'state/owner_maintenance.lock')
    # The real owner MODEL_UPDATE uses this separate maintenance flag.
    # Its omission made a stopped server appear to have no known maintenance
    # even when the owner had deliberately fenced it. Never infer a lease.
    owner_maintenance = kind(root / 'state/OWNER_MAINTENANCE.flag')
    # Neither a lock-file's existence nor a STOP absence is an owner writer lease.
    services = {}
    for name in ('nox-chat-8081', 'nox-dispatcher-t855u', 'nox-priority-scheduler',
                 'nox-selfheal', 'nox-gpu-watchdog-t865u'):
        rc, output = run(['supervisorctl', 'status', name], timeout=8)
        lines = output.strip().splitlines()
        match = re.match(r'^' + re.escape(name) + r'\s+([A-Z]+)(?:\s+pid\s+(\d+)\b)?',
                         lines[0]) if len(lines) == 1 else None
        status = match.group(1) if match else 'UNKNOWN'
        pid = int(match.group(2)) if match and match.group(2) else None
        # Nonzero supervisorctl cannot attest a RUNNING PID. A RUNNING row
        # without pid also fails closed; legitimate STOPPED (rc=3) remains visible.
        if status == 'RUNNING' and (rc != 0 or pid is None):
            status = 'UNKNOWN_SUPERVISOR_RUNNING_IDENTITY'
            pid = None
        start_ticks = None
        if pid:
            try:
                start_ticks = int((PROC / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()[19])
            except (OSError, IndexError, ValueError):
                status = 'UNKNOWN_PID_IDENTITY'
        services[name] = {'supervisor_rc': rc, 'state': status, 'pid': pid,
                          'start_ticks': start_ticks}
    inodes = set()
    net_status = 'OBSERVED'
    for net in (PROC / 'net/tcp', PROC / 'net/tcp6'):
        try:
            for line in net.read_text().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 10 and parts[3] == '0A' and int(parts[1].rsplit(':', 1)[1], 16) == 8081:
                    inodes.add(parts[9])
        except (OSError, IndexError, ValueError):
            net_status = 'UNKNOWN_NETWORK_NAMESPACE'
    owners = []
    if inodes:
        try:
            for proc in PROC.iterdir():
                if not proc.name.isdecimal():
                    continue
                for fd in (proc / 'fd').iterdir():
                    try:
                        target = os.readlink(fd)
                    except OSError:
                        continue
                    if target.startswith('socket:[') and target[8:-1] in inodes:
                        try:
                            ticks = int((proc / 'stat').read_text().rsplit(') ', 1)[1].split()[19])
                            owners.append({'pid': int(proc.name), 'start_ticks': ticks})
                        except (OSError, ValueError, IndexError):
                            owners.append({'pid': int(proc.name), 'start_ticks': None})
                        break
        except OSError:
            net_status = 'UNKNOWN_PID_SOCKET_MAPPING'
    if inodes and not owners and net_status == 'OBSERVED':
        net_status = 'UNRESOLVED_LISTENER_OWNER'
    heartbeat = {}
    for name in ('status/dispatcher_t855u.json', 'status/agents_t856u.json'):
        path = root / name
        if kind(path) == 'PRESENT':
            try:
                heartbeat[name] = {'mtime_ns': path.stat().st_mtime_ns,
                                   'scope': 'FILE_MTIME_ONLY_NOT_HEARTBEAT_PROOF'}
            except OSError:
                heartbeat[name] = {'state': 'UNKNOWN'}
        else:
            heartbeat[name] = {'state': kind(path)}
    return {'schema': 'NOX_OWNER_SAFETY_READONLY_V1',
            'stop_flags': flags, 'manual_stop': owner_stop,
            'owner_maintenance_flag': owner_maintenance,
            'maintenance_lock_file': maintenance_lock,
            'writer_lease': 'UNKNOWN_NO_OWNER_CAS_READBACK',
            'supervisor': services,
            'listener_8081': {'status': net_status,
                              'socket_inodes_observed': len(inodes),
                              'matched_pids': owners[:10],
                              'complete_pid_map': len(owners) <= 10 and net_status == 'OBSERVED'},
            'dispatcher_heartbeat_files': heartbeat,
            'admission': 'READ_ONLY_NO_RESTART_NO_DELETE_NO_TRAINER'}

MAYA_P0_BINARY_REL = 'engine_builds/maya-c81fab6c9d63-cu124-sm70-v1/build/maya-ds4'
MAYA_P0_BINARY_SHA256 = '3783980bb65861de36fe4d93b8e6bbd6b6a631207677bcabf330bf7830c21b20'

def maya_p0_binary_readback(root=None, expected_sha256=None):
    """Read-only SHA/ELF pin of original Maya; NEVER packs or runs model."""
    root = ROOT if root is None else Path(root)
    expected = MAYA_P0_BINARY_SHA256 if expected_sha256 is None else expected_sha256
    path = root / MAYA_P0_BINARY_REL
    result = {'schema':'NOX_MAYA_P0_BINARY_READONLY_V1', 'path':str(path),
              'pinned_sha256':expected, 'observed_sha256':None,
              'state':'HOLD_UNKNOWN', 'cuda124_runtime':'NOT_TESTED',
              'sm70_kernel':'NOT_TESTED', 'model_pack':'NOT_TESTED',
              'real_inference':'NOT_TESTED', 'native_model_promotion':False}
    try:
        # Refuse symlinks in the absolute owner path, including ancestors.
        for parent in (root, *tuple(path.parents)[:-1]):
            if not parent.is_relative_to(root):
                continue
            if not stat.S_ISDIR(parent.lstat().st_mode):
                result['state']='HOLD_UNSAFE_PARENT'; return result
        if stat.S_ISLNK(path.lstat().st_mode):
            result['state']='HOLD_SYMLINK_BINARY'; return result
        fd = os.open(path, os.O_RDONLY | getattr(os,'O_NOFOLLOW',0))
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not (before.st_mode & 0o111):
                result['state']='HOLD_NOT_EXECUTABLE_REGULAR'; return result
            if not 64 <= before.st_size <= 1024**3:
                result['state']='HOLD_BINARY_SIZE'; return result
            digest = hashlib.sha256()
            with os.fdopen(fd,'rb',closefd=False) as stream:
                first = stream.read(64)
                digest.update(first)
                if (first[:4] != b'\x7fELF' or first[4] != 2 or first[5] != 1
                        or int.from_bytes(first[18:20],'little') != 62):
                    result['state']='HOLD_NOT_LINUX_X86_64_ELF'; return result
                while block := stream.read(8*1024*1024):
                    digest.update(block)
            after = os.fstat(fd)
            identity = lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            if identity(before) != identity(after):
                result['state']='HOLD_BINARY_CHANGED_DURING_READ'; return result
            result['bytes']=before.st_size
            result['observed_sha256']=digest.hexdigest()
            result['state']=('SHA_PIN_MATCH_ELF_ONLY' if result['observed_sha256']==expected
                              else 'HOLD_BINARY_SHA_MISMATCH')
            return result
        finally:
            os.close(fd)
    except FileNotFoundError:
        result['state']='HOLD_BINARY_NOT_PRESENT'
    except (OSError, ValueError):
        result['state']='HOLD_BINARY_IO_OR_PATH'
    return result

def maya_elf_linkage_readback(root=None):
    """Read the pinned Maya ELF's dynamic section with readelf; never invoke Maya."""
    root = ROOT if root is None else Path(root)
    result = {'schema':'NOX_MAYA_ELF_LINKAGE_READONLY_V1',
              'path':str(root / MAYA_P0_BINARY_REL),
              'pinned_sha256':MAYA_P0_BINARY_SHA256,
              'observed_sha256':None,'bytes':None,'state':'HOLD_UNKNOWN',
              'needed_sonames':[],'rpath':[],'cuda_driver_direct_needed':False,'cuda_driver_expected_at_runtime':False,
              'cuda_runtime_needed':False,'cublas_needed':False,
              'maya_executable_invoked':False,'cuda_context_created':False,
              'dependency_resolution':'NOT_TESTED'}
    pin = maya_p0_binary_readback(root=root)
    result['observed_sha256'] = pin.get('observed_sha256')
    result['bytes'] = pin.get('bytes')
    if pin.get('state') != 'SHA_PIN_MATCH_ELF_ONLY':
        result['state'] = 'HOLD_BINARY_PIN'
        return result
    readelf = shutil.which('readelf')
    if not readelf:
        result['state'] = 'HOLD_READELF_UNAVAILABLE'
        return result
    try:
        cp = subprocess.run([readelf, '-d', '--wide', result['path']],
                            shell=False, check=False, capture_output=True,
                            text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        result['state'] = 'HOLD_READELF_FAILED'
        return result
    if cp.returncode != 0:
        result['state'] = 'HOLD_READELF_FAILED'
        return result
    needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', cp.stdout)
    paths = re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^\]]*)\]', cp.stdout)
    result['needed_sonames'] = needed[:128]
    result['rpath'] = paths[:8]
    result['cuda_driver_direct_needed'] = any(x.startswith('libcuda.so') for x in needed)
    result['cuda_runtime_needed'] = any(x.startswith('libcudart.so') for x in needed)
    result['cuda_driver_expected_at_runtime'] = result['cuda_runtime_needed']
    result['cublas_needed'] = any(x.startswith(('libcublas.so', 'libcublasLt.so')) for x in needed)
    result['state'] = 'ELF_LINKAGE_READ_ONLY'
    return result

def maya_dependency_path_readback(linkage=None):
    """Stat expected CUDA DSOs in ldconfig cache or ELF RPATH; never load a DSO."""
    linkage = maya_elf_linkage_readback() if linkage is None else linkage
    result = {'schema':'NOX_MAYA_DEPENDENCY_PATHS_READONLY_V1',
              'state':'HOLD_UNKNOWN','method':'LDCONFIG_CACHE_AND_ELF_RPATH_STAT_ONLY',
              'libraries':{},'maya_executable_invoked':False,
              'cuda_context_created':False,'runtime_abi':'NOT_TESTED'}
    if linkage.get('state') != 'ELF_LINKAGE_READ_ONLY':
        result['state'] = 'HOLD_ELF_LINKAGE'
        return result
    ldconfig = shutil.which('ldconfig')
    if not ldconfig:
        result['state'] = 'HOLD_LDCONFIG_UNAVAILABLE'
        return result
    try:
        cp = subprocess.run([ldconfig, '-p'], shell=False, check=False,
                            capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        result['state'] = 'HOLD_LDCONFIG_FAILED'
        return result
    if cp.returncode != 0 or len(cp.stdout) > 1024 * 1024:
        result['state'] = 'HOLD_LDCONFIG_FAILED'
        return result
    names = ('libcuda.so.1','libcudart.so.12','libcublas.so.12','libcublasLt.so.12')
    cache = {name:[] for name in names}
    for line in cp.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] in cache and fields[-2] == '=>':
            cache[fields[0]].append(fields[-1])
    rpaths = [x for x in linkage.get('rpath',[]) if isinstance(x,str)]
    for name in names:
        paths = list(dict.fromkeys(cache[name] + [str(Path(base) / name) for base in rpaths]))
        found = []
        for candidate in paths[:32]:
            try:
                p = Path(candidate)
                if p.is_file():
                    found.append({'path':candidate,'resolved_path':str(p.resolve(strict=True))})
            except (OSError, RuntimeError):
                pass
        result['libraries'][name] = {'present':bool(found),'candidates':found[:8]}
    result['state'] = ('AVAILABLE_PATHS_ONLY' if all(result['libraries'][n]['present'] for n in names)
                       else 'HOLD_REQUIRED_LIBRARY_PATH_MISSING')
    cuda_paths = result['libraries']['libcuda.so.1']['candidates']
    rt_paths = result['libraries']['libcudart.so.12']['candidates']
    result['driver_path_hint'] = cuda_paths[0]['resolved_path'] if cuda_paths else None
    result['toolkit_path_hint'] = rt_paths[0]['resolved_path'] if rt_paths else None
    result['cuda_toolkit_path_version_hint'] = (
        '12.4' if any('/cuda-12.4/' in row['resolved_path'] for row in rt_paths) else 'UNKNOWN')
    return result

def worker(i):
    f=(hardware,processes,training,controls,chat_storage,receipts)[i]
    try: return {'section':f.__name__,'worker_pid':os.getpid(),'result':f()}
    except Exception as e: return {'section':f.__name__,'worker_pid':os.getpid(),'error':type(e).__name__}

if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=6) as pool:
        for row in pool.map(worker,range(6)):
            # Each source record has its own bounded line; a long controller must
            # not hide all controls behind the transport's per-line safety cap.
            items=[dict(row,result=[item]) for item in row.get('result',[])] if row['section']=='controls' and isinstance(row.get('result'),list) else [row]
            for item in items:
                print('NOX_MAINT_INSPECT='+json.dumps(item,separators=(',',':')),flush=True)
    owner_component_readback()
    print('NOX_MAINT_SAFETY=' + json.dumps(owner_safety_snapshot(), separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_MAYA_P0=' + json.dumps(maya_p0_binary_readback(), separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_MAYA_ELF_LINKAGE=' + json.dumps(maya_elf_linkage_readback(), separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_MAYA_DEPENDENCIES=' + json.dumps(maya_dependency_path_readback(), separators=(',', ':'), allow_nan=False), flush=True)
    bounded_capacity_readback()
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)
