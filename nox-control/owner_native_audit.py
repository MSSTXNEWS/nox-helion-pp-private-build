#!/usr/bin/env python3
"""One-shot native audit. Seven bounded OS workers, no daemon, no mutation or credentials output."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json, os, re, shutil, subprocess, sys, time

SAFE=re.compile(r'^[A-Za-z0-9_./+@:= -]{1,300}$')
ROOTS=('/root/nox','/root/nox_learn','/workspace')

def run(argv, seconds=12):
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=seconds)
        return p.returncode,p.stdout[:200000]
    except Exception as e:return 99,type(e).__name__

def num(path):
    try:
        v=Path(path).read_text().strip()
        return int(v) if v.isdigit() else v[:40]
    except OSError:return None

def hardware():
    rc,g=run(['nvidia-smi','--query-gpu=index,name,uuid,memory.total,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'])
    _,a=run(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_gpu_memory','--format=csv,noheader,nounits'])
    return {'gpu_rc':rc,'gpu':[x for x in g.splitlines() if SAFE.fullmatch(x.replace(',',''))][:4],
      'gpu_apps':[x for x in a.splitlines() if SAFE.fullmatch(x.replace(',',''))][:16],
      'cpus':os.cpu_count(),'load':list(os.getloadavg()),
      'cgroup_max':num('/sys/fs/cgroup/memory.max'),'cgroup_current':num('/sys/fs/cgroup/memory.current'),
      'cpu_max':num('/sys/fs/cgroup/cpu.max'),
      'disk':{r:dict(zip(('total','used','free'),shutil.disk_usage(r))) for r in ROOTS if Path(r).is_dir()}}

def process_rows():
    rows=[]
    flags={'-m','--model','--model-path','--model_path','--base-model','--student','--output_dir','--output-dir','--config','-c'}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if not argv or not any(k in ' '.join(argv[:3]).lower() for k in ('nox','llama','train','python','supervisor','rclone','jupyter')):continue
            args=[]
            for i,v in enumerate(argv):
                if v in flags and i+1<len(argv) and SAFE.fullmatch(argv[i+1]) and '://' not in argv[i+1]:args.append([v,argv[i+1]])
            row={'pid':int(p.name),'comm':(p/'comm').read_text().strip()[:60],
                 'executable':os.path.basename(argv[0]),'arguments':args[:12]}
            scripts=[v for v in argv[1:5] if v.endswith(('.py','.sh')) and SAFE.fullmatch(v)]
            if scripts:row['scripts']=scripts
            rows.append(row)
        except (OSError,ValueError):continue
    return rows[:100]

def supervisor():
    binary=shutil.which('supervisorctl')
    if not binary:
        binary=next((x for x in ('/opt/venv/bin/supervisorctl','/usr/local/bin/supervisorctl') if Path(x).is_file()),None)
    if not binary:return {'available':False}
    candidates=[None]+[x for x in ('/etc/supervisor/supervisord.conf','/etc/supervisord.conf','/root/nox/supervisord.conf') if Path(x).is_file()]
    results=[]
    for c in candidates:
        args=[binary]+(['-c',c] if c else [])+['status']
        rc,out=run(args)
        rows=[]
        for line in out.splitlines():
            m=re.match(r'^([A-Za-z0-9_.:-]+)\s+(RUNNING|STARTING|STOPPED|FATAL|BACKOFF|EXITED|STOPPING|UNKNOWN)\b(.*)$',line)
            if m:
                pid=re.search(r'\bpid (\d+)',m.group(3))
                rows.append({'name':m.group(1),'state':m.group(2),'pid':int(pid[1]) if pid else None})
        results.append({'config':c,'rc':rc,'services':rows})
        if rows:break
    return {'available':True,'results':results}

def packages():
    code="import importlib.metadata as m,json; names=['torch','transformers','accelerate','datasets','deepspeed','safetensors','peft','bitsandbytes','trl','psutil','nvidia-ml-py']; d={};\nfor n in names:\n try:d[n]=m.version(n)\n except m.PackageNotFoundError:d[n]=None\nprint(json.dumps(d))"
    found={}
    for p in ('/opt/venv/bin/python','/root/nox/.venv/bin/python','/usr/bin/python3'):
        if Path(p).is_file():
            rc,out=run([p,'-c',code])
            try:found[p]=json.loads(out) if rc==0 else {'status':'IMPORT_FAILED'}
            except ValueError:found[p]={'status':'INVALID_OUTPUT'}
    return found

def models():
    result=[]; deadline=time.monotonic()+25
    for root in ROOTS:
        if not Path(root).is_dir():continue
        base_depth=len(Path(root).parts)
        for directory,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[x for x in dirs if x not in ('.git','node_modules','.venv','venv','site-packages','__pycache__') and not Path(directory,x).is_symlink()]
            if len(Path(directory).parts)-base_depth>=7:dirs[:]=[]
            for name in files:
                if time.monotonic()>deadline or len(result)>=180:return {'files':result,'truncated':True}
                p=Path(directory,name)
                if p.is_symlink():continue
                if p.suffix.lower() in ('.gguf','.safetensors') or name in ('config.json','trainer_state.json','adapter_config.json','rclone.conf'):
                    try:
                        s=p.stat(); row={'path':str(p),'bytes':s.st_size,'mtime':int(s.st_mtime)}
                        if name=='rclone.conf':row={'rclone_config_present':True};result.append(row);continue
                        if name in ('config.json','adapter_config.json','trainer_state.json') and s.st_size<2_000_000:
                            d=json.loads(p.read_text())
                            for key in ('model_type','architectures','global_step','base_model_name_or_path','peft_type','r'):
                                if key in d and isinstance(d[key],(str,int,list,type(None))):row[key]=d[key]
                            if name=='trainer_state.json':row['log_entries']=len(d.get('log_history',[]))
                        result.append(row)
                    except (OSError,ValueError,TypeError):pass
    return {'files':result,'truncated':False}

def storage():
    rc=shutil.which('rclone')
    if not rc:return {'rclone_present':False}
    status,out=run([rc,'listremotes'])
    names=[x.strip() for x in out.splitlines() if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}:',x.strip())]
    checks=[]
    for remote in names[:3]:
        code,out=run([rc,'about',remote,'--json'],15)
        try:
            d=json.loads(out);clean={k:d[k] for k in ('total','used','free','trashed') if type(d.get(k)) is int}
        except (ValueError,TypeError):clean={}
        checks.append({'remote':remote,'about_rc':code,'capacity':clean})
    return {'rclone_present':True,'list_rc':status,'remotes':names,'checks':checks,
            'known_config_present':{x:Path(x).is_file() for x in ('/root/.config/rclone/rclone.conf','/root/nox/rclone.conf')}}

# Read only the current Linux mount namespace. Device source strings are intentionally
# omitted because they can contain remote paths or credentials. statvfs reads metadata only.
BLOCK_FILESYSTEMS={'ext2','ext3','ext4','xfs','btrfs','zfs','vfat','exfat','ntfs'}
def _unescape_mountinfo(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m.group(1),8)),value)

def _mount_inventory_from_text(text,statvfs=os.statvfs):
    rows=[]; seen=set(); eligible=0
    lines=text.splitlines()
    truncated=len(lines)>4096
    for line in lines[:4096]:
        try:
            before,after=line.split(' - ',1)
            left=before.split(); right=after.split()
            if len(left)<6 or len(right)<3:continue
            fstype=right[0]
            if fstype not in BLOCK_FILESYSTEMS:continue
            mountpoint=_unescape_mountinfo(left[4])
            dev=left[2]
            if mountpoint in seen or not SAFE.fullmatch(mountpoint) or not re.fullmatch(r'\d+:\d+',dev):continue
            eligible+=1
            if len(rows)>=512:
                truncated=True
                continue
            try:
                st=statvfs(mountpoint)
                block_size=st.f_frsize or st.f_bsize
                total=int(st.f_blocks)*int(block_size)
                available=int(st.f_bavail)*int(block_size)
            except (OSError,AttributeError,TypeError,ValueError):
                total=None; available=None
            seen.add(mountpoint)
            rows.append({'mountpoint':mountpoint,'filesystem':fstype,'device_major_minor':dev,
                         'total_bytes':total,'available_bytes':available})
        except (ValueError,IndexError):continue
    rows.sort(key=lambda r:(r['mountpoint'],r['filesystem'],r['device_major_minor']))
    return {'scope':'current_process_mount_namespace_only','provider_disk_visibility':'not_established',
            'mountinfo_readable':True,'data_mount_present':any(r['mountpoint']=='/data' for r in rows),
            'eligible_block_mount_count':eligible,'truncated':truncated,'mounts':rows}

def mount_inventory():
    try:
        text=Path('/proc/self/mountinfo').read_text()
    except OSError as e:
        return {'scope':'current_process_mount_namespace_only','mountinfo_readable':False,
                'error':type(e).__name__,'mounts':[]}
    return _mount_inventory_from_text(text)

def worker(i):
    try:
        functions=(hardware,process_rows,supervisor,packages,models,storage,mount_inventory)
        return {'section':functions[i].__name__,'worker_pid':os.getpid(),'result':functions[i]()}
    except Exception as e:return {'section':str(i),'worker_pid':os.getpid(),'error':type(e).__name__}

def main():
    with ProcessPoolExecutor(max_workers=7) as pool:
        for row in pool.map(worker,range(7)):
            # One JSON record per bounded result item; never dump env/config secrets.
            print('NOX_MAINT_AUDIT='+json.dumps(row,separators=(',',':')),flush=True)
    print('NOX_MAINT_AUDIT_COMPLETE=true',flush=True)
if __name__=='__main__':main()

