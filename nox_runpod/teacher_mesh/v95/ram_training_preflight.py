"""NOX V95 one native read-only RAM/offload/trainer runtime baseline.

Uses existing NOX2 V51 route, no new service or model process, no torch CUDA
initialization, and no memory-content export.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as native
old=native.api
def settle(method,path,key,data=None):
    result=old(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(12)
    return result
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib,importlib.metadata,json,os,re,subprocess,sys
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V95_SCHEMA=NOX_RAM_BASE_WEIGHT_TRAINING_PREFLIGHT_V1')
def emit(label,payload):
    print('NATIVE_V95_'+label+'='+json.dumps(payload,sort_keys=True,separators=(',',':'))[:1400])
def call(args,secs=6):
    try:
        return subprocess.run(args,capture_output=True,text=True,timeout=secs)
    except (OSError,subprocess.TimeoutExpired):
        return None
kv={}
try:
    for line in Path('/proc/meminfo').read_text().splitlines():
        if ':' not in line:continue
        name,val=line.split(':',1)
        if name in ('MemAvailable','MemTotal','Cached','Dirty','Shmem','SwapFree'):
            kv[name+'_bytes']=int(val.split()[0])*1024
except (OSError,ValueError):pass
for label,path in (('tmpfs','/dev/shm'),('workspace','/workspace')):
    try:
        s=os.statvfs(path)
        kv[label+'_free_bytes']=s.f_frsize*s.f_bavail
    except OSError:pass
for label,file in (('cgroup_max','/sys/fs/cgroup/memory.max'),
                   ('cgroup_current','/sys/fs/cgroup/memory.current'),
                   ('cgroup_v1_limit','/sys/fs/cgroup/memory/memory.limit_in_bytes')):
    try:
        value=Path(file).read_text().strip()
        kv[label]=int(value) if value.isdigit() else value[:32]
    except (OSError,ValueError):pass
emit('RAM',kv)

# Metadata only: do not import torch and create an accidental CUDA context.
packages=('torch','transformers','accelerate','datasets','trl','safetensors',
          'huggingface-hub','bitsandbytes','deepspeed','peft','numpy')
pythons={sys.executable}
for folder in ('/root/nox/.venv','/root/nox/venv','/workspace/.venv',
               '/opt/conda','/root/nox/tools/ai-accelerators/v94'):
    exe=Path(folder)/'bin/python'
    if exe.exists():pythons.add(str(exe))
seen=0
for folder in ('/root/nox','/workspace'):
    root=Path(folder)
    for pat in ('*/bin/python','*/*/bin/python'):
        for exe in root.glob(pat):
            if exe.is_file() and not exe.is_symlink():
                pythons.add(str(exe))
                if len(pythons)>18:break
for py in sorted(pythons)[:12]:
    cmd=[py,'-c',("import importlib.metadata as m,json,sys;"
                  "names="+repr(packages)+"; v={};"
                  "\nfor name in names:\n"
                  " try:v[name]=m.version(name)\n"
                  " except m.PackageNotFoundError:pass\n"
                  "print(json.dumps({'packages':v,'python':sys.version.split()[0]}))")]
    x=call(cmd,6)
    if x and x.returncode==0:
        try:obj=json.loads(x.stdout.strip().splitlines()[-1])
        except (ValueError,IndexError):continue
        if obj.get('packages'):
            emit('TRAINING_ENV',{'exe_hint':hashlib.sha256(py.encode()).hexdigest()[:12],
                                 **obj})
            seen+=1
emit('TRAINING_ENV_COUNT',{'environments_with_packages':seen})

model={}
root=Path('/root/nox')
for p,dirs,files in os.walk(root,followlinks=False):
    dirs[:]=[d for d in dirs if d not in ('.git','.cache','venv','__pycache__',
              'site-packages','node_modules','logs','.ssh') and not (Path(p)/d).is_symlink()][:125]
    h=hashlib.sha256(p.encode()).hexdigest()[:16]
    if h=='e646ed03a2d1992e':
        model={'directory_hash16':h,'shards':sum(n.endswith('.safetensors') for n in files),
               'config': 'config.json' in files,
               'shard_index':'model.safetensors.index.json' in files,
               'available_on_cpu_disk':True,'trainable_on_gpu1_verified':False}
        break
emit('MODEL',model)
g=call(['nvidia-smi','--query-gpu=index,name,compute_cap,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'])
rows=[]
if g and g.returncode==0:
    for line in g.stdout.splitlines()[:2]:
        parts=[x.strip() for x in line.split(',')]
        if len(parts)==8:
            try:
                rows.append({'index':int(parts[0]),'name':parts[1],
                  'sm':parts[2], 'vram_total_mib':int(parts[3]),
                  'vram_free_mib':int(parts[4]),'vram_used_mib':int(parts[5]),
                  'utilization_pct':int(parts[6]),'temperature_c':int(parts[7])})
            except (TypeError,ValueError):pass
emit('GPUS',rows)
slots=None
try:
    import urllib.request
    with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as res:
        arr=json.load(res)
    if isinstance(arr,list):
        slots={'total':len(arr),'busy':sum(bool(x.get('is_processing')) for x in arr if isinstance(x,dict))}
except Exception:pass
emit('CHAT',{'slots':slots,'p0_reserved':True})
# Never claim offload as equivalent to verified full-model optimizer steps.
report={'can_use_os_ram_cache':True,'full_cpu_model_copy_requested':False,
 'whole_qwen_moe_67gib_in_devshm_allowed':False,
 'gpu1_training_admission':False,
 'reasons':['HOLD_SIGNED_ONEHOST_LEASE','HOLD_GPU1_PEAK_VRAM',
            'HOLD_TRAINABLE_NOX_STUDENT_AND_OWNER_KEY_RESTORE',
            'HOLD_APPROVED_TRAIN_HOLDOUT'],
 'cpu_ram_weights_can_be_page_cached':True,
 'background_ram_prep_allowed_if_chat_idle':True,
 'no_training_started':True}
emit('DECISION',report)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    native.REMOTE=REMOTE;native.api=settle
    buf=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(buf):ok=native.probe()
    except Exception as e:
        msg=str(e)
        print('NOX_V95_CONNECTION='+msg if msg.startswith('HOLD_') and len(msg)<90 else 'NOX_V95_CONNECTION=HOLD')
    finally:
        try:
            with contextlib.redirect_stdout(buf):
                if not native.cleanup():ok=False
        except Exception:ok=False
    lines=buf.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V95_','TEMP_SSH_CLEANUP=')) and len(line)<1600:
            print(line)
    passed=ok and any(x.startswith('NATIVE_V95_DECISION=') for x in lines)
    print('NOX_V95_RAM_TRAIN_PREFLIGHT='+('PASS' if passed else 'HOLD'))
    return 0 if passed else 2
if __name__=='__main__':
    raise SystemExit(main())
