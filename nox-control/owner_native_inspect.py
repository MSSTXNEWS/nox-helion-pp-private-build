#!/usr/bin/env python3
"""Six bounded read-only probes of existing NOX, without env/credential dumps."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import configparser, hashlib, json, os, re, shlex, shutil, subprocess, time, urllib.request
ROOT = Path('/root/nox')
PROC = Path('/proc')
SECRET = re.compile(r'(?i)(?:Bearer\s+\S+|(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}|(?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*[\"\'][^\"\']{12,})')
SENSITIVE_NAME = r'(?:password|secret|api[_-]?key|access[_-]?key|authorization|(?:hf|github|gh|api|auth|access|refresh|bearer|nox)[_-]?token|token|NOX2)'
SENSITIVE_ASSIGNMENT = re.compile(r'(?i)\b'+SENSITIVE_NAME+r'[\"\']?\s*[:=]\s*(?:[\"\'][^\"\'\n]*[\"\']|[^\s,;\n]+)')
SERVICES = ('nox-train-volta-t866u', 'nox-teacher-serve-t811u',
            'nox-train-worm-t811u', 'nox-autoscale-t877u', 'nox-dispatcher-t855u',
            'nox-gpu-watchdog-t865u', 'nox-vram-guard-t829u', 'nox-priority-scheduler')

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

def hardware():
    out = {}
    for label, query in (('gpu','index,uuid,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu'),('apps','pid,gpu_uuid,used_gpu_memory')):
        arg = '--query-gpu=' if label == 'gpu' else '--query-compute-apps='
        rc, s = run(['nvidia-smi', arg+query, '--format=csv,noheader,nounits'])
        out[label] = {'rc':rc, 'rows':s.splitlines()[:40]}
    out['cgroup'] = {n:text('/sys/fs/cgroup/'+n, 2048) for n in ('memory.max','memory.current','memory.events','cpu.max','cpu.stat')}
    out['disk'] = {p:dict(zip(('total','used','free'),shutil.disk_usage(p))) for p in ('/root/nox','/dev/shm') if Path(p).exists()}
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
            stat=(p/'stat').read_text().split(') ',1)[1].split()
            env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode(errors='replace').split('\0') if '=' in x)
            status=(p/'status').read_text()
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

def controls():
    configs=supervisor_config()
    names=['train_qlora_35b_t866u.py','run_train_volta_t866u.sh',
           'nox_autoscale_t877u.py','nox_dispatcher_t855u.py',
           'teacher_serve_t811u.sh','vram_guard_t829u.py','gpu_hang_watchdog_t865u.py']
    # Only exact training-service script references inside the known scripts root.
    for config in configs:
        if config['service']!='nox-train-volta-t866u':continue
        try:args=shlex.split(config['settings'].get('command',''))
        except ValueError:continue
        for arg in args:
            p=Path(arg)
            if p.parent==ROOT/'scripts' and re.fullmatch(r'[A-Za-z0-9_]*t866u\.(py|sh)',p.name) and p.name not in names:names.append(p.name)
    rows=[];remaining=65000
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
    out['memory_files']=[]
    for root in (ROOT/'memory',ROOT/'kb'):
        for p in root.glob('*.db'):
            st=p.stat();out['memory_files'].append({'path':str(p),'bytes':st.st_size,'mtime':st.st_mtime})
    return out

def receipts():
    rows=[]
    for p in sorted((ROOT/'state').glob('owner_maintenance_*.json'))[-8:]:
        try:
            d=json.loads(p.read_text());rows.append({'path':str(p),'data':d})
        except (OSError,ValueError):pass
    return rows

def worker(i):
    f=(hardware,processes,training,controls,chat_storage,receipts)[i]
    try: return {'section':f.__name__,'worker_pid':os.getpid(),'result':f()}
    except Exception as e: return {'section':f.__name__,'worker_pid':os.getpid(),'error':type(e).__name__}

if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=6) as pool:
        for row in pool.map(worker,range(6)):
            print('NOX_MAINT_INSPECT='+json.dumps(row,separators=(',',':')),flush=True)
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)
