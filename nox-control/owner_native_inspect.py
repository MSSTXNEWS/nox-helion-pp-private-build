#!/usr/bin/env python3
"""Six bounded read-only probes of existing NOX, without env/credential dumps."""
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, time, urllib.request
ROOT = Path('/root/nox')
SECRET = re.compile(r'(?i)(?:Bearer\s+\S+|(?:hf_|ghp_|github_pat_)[A-Za-z0-9_]{12,}|(?:password|secret|api_key|access_key|authorization|token)\s*[:=]\s*[\"\'][^\"\']{12,})')

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
    for p in Path('/proc').iterdir():
        if not p.name.isdigit(): continue
        try:
            argv=(p/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if not argv or not any(x in ' '.join(argv[:3]) for x in ('nox','llama','train','supervisor')): continue
            stat=(p/'stat').read_text().split(') ',1)[1].split()
            env=dict(x.split('=',1) for x in (p/'environ').read_bytes().decode(errors='replace').split('\0') if '=' in x)
            status=(p/'status').read_text()
            row={'pid':int(p.name),'ppid':int(stat[1]),'state':stat[0],'starttime':stat[19], 'exe':os.path.basename(argv[0]),'cuda':env.get('CUDA_VISIBLE_DEVICES'),'proc_name':env.get('PROC_NAME')}
            row['scripts']=[v for v in argv[1:4] if v.endswith(('.py','.sh')) and len(v)<250 and '\n' not in v]
            row['args']={k:argv[i+1] for i,k in enumerate(argv[:-1]) if k in ('-m','--model','--port','-t','-np','--max-steps','--n-gpu-layers','-ngl') and len(argv[i+1])<250}
            for k in ('NSpid','VmRSS','Threads'):
                m=re.search(r'^'+k+r':\s*(.+)$',status,re.M)
                if m: row[k]=m[1]
            rows.append(row)
        except (OSError,ValueError,IndexError): pass
    return rows[:120]

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
    return rows

def controls():
    rows=[]
    for name in ('nox_autoscale_t877u.py','nox_dispatcher_t855u.py','gpu_hang_watchdog_t865u.py','vram_guard_t829u.py','teacher_serve_t811u.sh'):
        p=ROOT/'scripts'/name
        if not p.is_file(): continue
        b=p.read_bytes(); row={'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
        s=b.decode(errors='replace')
        if name in ('nox_autoscale_t877u.py','gpu_hang_watchdog_t865u.py') and len(b)<40000 and not SECRET.search(s): row['source']=s
        else:
            lines=s.splitlines(); indexes=set()
            for i,line in enumerate(lines):
                if re.search(r'train_wants_gpu1|nox-train-volta|TRAIN_HOLD|supervisorctl|train_qlora|SIGKILL|SIGSTOP',line): indexes.update(range(max(0,i-4),min(len(lines),i+7)))
            row['excerpts']=[f'{i+1}: '+SECRET.sub('[REDACTED]',lines[i]) for i in sorted(indexes)][:180]
        rows.append(row)
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
