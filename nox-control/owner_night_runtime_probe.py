#!/usr/bin/env python3
"""Read-only, bounded NOX runtime/storage facts; no service or data mutations."""
from __future__ import annotations
import ast
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import time

ROOT = Path('/root/nox')
MAX_SOURCE = 2 * 1024 * 1024

def emit(section, value):
    raw = json.dumps({'section': section, 'value': value}, ensure_ascii=True, separators=(',', ':'))
    if len(raw) > 150000:
        raise RuntimeError('HOLD_PROBE_OUTPUT_BUDGET')
    print('NOX_MAINT_NIGHT_PROBE=' + raw, flush=True)

def read(path, limit=MAX_SOURCE):
    with open(path, 'rb') as f:
        value = f.read(limit + 1)
    if len(value) > limit:
        raise ValueError('input_too_large')
    return value

def metadata(path):
    try:
        p = Path(path); s = p.lstat()
        return {'path': str(p), 'bytes': s.st_size, 'allocated_bytes': s.st_blocks * 512,
                'mtime_ns': s.st_mtime_ns, 'inode': s.st_ino, 'uid': s.st_uid,
                'mode': oct(stat.S_IMODE(s.st_mode)), 'symlink': stat.S_ISLNK(s.st_mode)}
    except OSError as e:
        return {'path': str(path), 'error': type(e).__name__}

def run(argv, timeout=15):
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': ''}
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    return {'returncode': p.returncode, 'stdout': p.stdout[:32000],
            'stderr_tail': p.stderr[-1000:]}

def resources():
    cg = Path('/sys/fs/cgroup')
    keys = ('memory.max', 'memory.current', 'memory.high', 'memory.pressure', 'cpu.max', 'memory.events')
    data = {'cgroup': {k: read(cg/k, 65536).decode() for k in keys if (cg/k).exists()},
            'disk': {str(p): dict(zip(('total', 'used', 'free'), shutil.disk_usage(p)))
                     for p in (ROOT, Path('/dev/shm'))},
            'stops': [metadata(p) for p in [ROOT/'STOP', ROOT/'STOP.flag', ROOT/'state/STOP',
                ROOT/'state/TRAIN_HOLD.flag', ROOT/'state/OWNER_MAINTENANCE.flag',
                ROOT/'state/forge_training.lock', ROOT/'state/owner_maintenance.lock'] if p.exists()],
            'mutations_performed': False}
    status = read('/proc/self/status', 65536).decode()
    caps = re.search(r'^CapEff:\s+([0-9a-fA-F]+)$', status, re.M)
    data['cap_sys_admin_present'] = bool(caps and int(caps[1], 16) & (1 << 21))
    data['supervisor'] = run(['supervisorctl', 'status'])
    data['gpu'] = run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'])
    return data

PY_PROBE = r'''
import importlib.metadata as m,json,os,platform,sys
d={'executable':sys.executable,'python':sys.version,'platform':platform.platform(),'packages':{}}
for n in ['torch','transformers','peft','accelerate','bitsandbytes','tokenizers','numpy','safetensors','trl','datasets']:
 try:
  p=m.distribution(n);d['packages'][n]={'version':p.version,'location':str(p.locate_file(''))}
 except m.PackageNotFoundError:d['packages'][n]=None
try:
 import torch
 d['torch']={'version':torch.__version__,'cuda_build':torch.version.cuda,'cuda_initialized':torch.cuda.is_initialized(),'arch_flags':getattr(torch._C,'_cuda_getArchFlags',lambda:None)()}
except Exception as e:d['torch_error']={'type':type(e).__name__,'message':str(e)[:500]}
print(json.dumps(d,sort_keys=True))
'''

def python_info():
    result = []
    for p in (Path('/root/venv_volta/bin/python'), ROOT/'venv/bin/python', Path('/usr/bin/python3')):
        if not p.exists():
            continue
        try:
            result.append({'path': str(p), **run([str(p), '-c', PY_PROBE], timeout=25)})
        except subprocess.TimeoutExpired:
            result.append({'path': str(p), 'error': 'timeout'})
    return result

def shm_inventory():
    base = Path('/dev/shm'); top = []; files = []; count = 0; deadline = time.monotonic() + 15
    for entry in sorted(base.iterdir()):
        row = metadata(entry)
        if not entry.name.lower().startswith('nox') or entry.is_symlink() or not entry.is_dir():
            top.append(row); continue
        size = allocated = 0
        for folder, dirs, names in os.walk(entry, followlinks=False):
            dirs[:] = [n for n in dirs if not (Path(folder)/n).is_symlink()]
            for name in names:
                if count >= 10000 or time.monotonic() > deadline:
                    row['truncated'] = True; break
                p = Path(folder)/name
                try: s = p.lstat()
                except OSError: continue
                count += 1
                if stat.S_ISREG(s.st_mode):
                    size += s.st_size; allocated += s.st_blocks * 512
                    if s.st_size >= 100000000: files.append(metadata(p))
            if row.get('truncated'): break
        row.update(logical_bytes=size, allocated_total_bytes=allocated); top.append(row)
    large = sorted(files, key=lambda x:x['bytes'], reverse=True)[:50]
    candidates = {x['path']: x for x in large}
    for value in candidates.values(): value['observed_readers'] = []
    scan_deadline = time.monotonic() + 12; scanned = 0; truncated = False
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        if time.monotonic() > scan_deadline: truncated = True; break
        try:
            scanned += 1
            opened = set()
            for fd in (proc/'fd').iterdir():
                try: opened.add(os.readlink(fd).removesuffix(' (deleted)'))
                except OSError: pass
            maps = read(proc/'maps', 2*1024*1024).decode(errors='replace')
            for name, row in candidates.items():
                if name in opened or name in maps:
                    row['observed_readers'].append(int(proc.name))
        except (OSError, ValueError): continue
    return {'top_entries': top[:80], 'large_files': large, 'file_count_scanned': count,
            'processes_scanned': scanned, 'reader_scan_truncated': truncated,
            'absence_of_observed_reader_is_not_reclaim_authorization': True}

def source_info():
    names = ('nox_dispatcher_t855u.py','owner_task_plans.py','owner_task_lifecycle.py',
             'owner_dispatcher_mentor.py','owner_event_outbox.py','s03_memory.py','nox_journal.py',
             'hybrid_training_entry.py','train_qlora_35b_t866u.py','owner_autonomy_pool.py',
             'owner_subagent_processes.py')
    rows = []
    for name in names:
        p = ROOT/'scripts'/name; row = metadata(p)
        if 'error' in row: rows.append(row); continue
        try:
            raw = read(p); row['sha256'] = hashlib.sha256(raw).hexdigest()
            tree = ast.parse(raw.decode()); row['public_functions'] = []
            if name in ('s03_memory.py','nox_journal.py'):
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith('_'):
                        row['public_functions'].append({'name':node.name,'args':[a.arg for a in node.args.args],
                          'calls':sorted({ast.unparse(n.func) for n in ast.walk(node) if isinstance(n,ast.Call)})[:45]})
                row['database_paths'] = sorted({n.value for n in ast.walk(tree) if isinstance(n,ast.Constant)
                    and isinstance(n.value,str) and n.value.startswith('/root/nox/') and n.value.endswith(('.db','.sqlite','.sqlite3'))})
        except (OSError,ValueError,SyntaxError,UnicodeError) as e: row['parse_error']=type(e).__name__
        rows.append(row)
    return rows

def dispatcher_state():
    p = ROOT/'state/dispatcher/state.json'
    try:
        d = json.loads(read(p,16*1024*1024)); tasks = d.get('tasks',{})
        counts = {}; active = []
        for key, v in tasks.items():
            if not isinstance(v,dict): continue
            status = v.get('status','unknown'); counts[status] = counts.get(status,0)+1
            if status == 'running' and len(active)<100:
                active.append({'id':str(key)[:160], **{k:v[k] for k in ('handler','pid','nonce','job_id','started','updated') if k in v and isinstance(v[k],(str,int,float,type(None)))}})
        return {'metadata':metadata(p),'counts':counts,'running':active}
    except (OSError,ValueError) as e: return {'error':type(e).__name__}

def supervisor_config():
    result=[]
    for p in sorted(Path('/etc/supervisor/conf.d').glob('*nox*'))[:50]:
        if not p.is_file():continue
        try:
            cp=configparser.ConfigParser(interpolation=None);cp.read_string(read(p,65536).decode())
            for section in cp.sections():
                if section.startswith('program:'):
                    keep={k:cp[section].get(k) for k in ('stopasgroup','killasgroup','autostart','autorestart','stopwaitsecs','stopsignal','user') if k in cp[section]}
                    keep.update(path=str(p),section=section,sha256=hashlib.sha256(read(p,65536)).hexdigest())
                    result.append(keep)
        except (OSError,ValueError,configparser.Error):result.append({'path':str(p),'error':'unreadable_config'})
    return result

def main():
    signal.alarm(145)
    emit('identity',{'schema':'NOX_NIGHT_RUNTIME_PROBE_V1','request':os.environ.get('NOX_OWNER_REQUEST_ID'),
         'source_sha':os.environ.get('NOX_OWNER_SOURCE_SHA'),'time_epoch':time.time(),'read_only':True})
    for name, fn in (('resources',resources),('python',python_info),('shm',shm_inventory),
                     ('source',source_info),('dispatcher',dispatcher_state),('supervisor_config',supervisor_config)):
        try:emit(name,fn())
        except Exception as e:emit(name,{'error_type':type(e).__name__})
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
