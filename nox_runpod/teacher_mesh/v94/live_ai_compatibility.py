"""NOX E2 V94: one read-only native AI performance / Volta compatibility inventory.

Probe existing container and OneHost; no installs, downloads, model changes,
live GPU allocations, service restarts or user content export.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
_old=ssh.api
def settle(method,path,key,data=None):
    val=_old(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(13)
    return val

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,sys,platform,subprocess,json,shutil,stat,re,importlib.metadata as metadata
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V94_SCHEMA=NOX_VOLTA_AI_PERF_COMPATIBILITY_V1')
def emit(k,v):
    print("NATIVE_V94_"+k+"="+json.dumps(v,separators=(',',':'),ensure_ascii=False,sort_keys=True)[:1800])
def run(args,seconds=8):
    try:return subprocess.run(args,text=True,capture_output=True,timeout=seconds)
    except Exception:return None
pkgs=("torch","torchvision","torchaudio","transformers","accelerate","trl",
 "peft","bitsandbytes","datasets","safetensors","huggingface-hub",
 "hf-xet","xformers","flash-attn","triton","vllm","llama-cpp-python",
 "sentencepiece","tokenizers","optimum","deepspeed","psutil","numpy",
 "orjson","zstandard","lz4","diskcache","faiss-cpu","rank-bm25",
 "rapidfuzz","uv","ninja","packaging","watchdog","ujson")
def versions(py):
    cmd=[py,'-c',("import json,sys,importlib.metadata as m;"
    "n="+repr(pkgs)+";"
    "v={};"
    "\nfor k in n:\n try:v[k]=m.version(k)\n except m.PackageNotFoundError:pass\n"
    "print(json.dumps({'python':sys.version.split()[0],'packages':v},sort_keys=True))")]
    z=run(cmd,18)
    if z and z.returncode==0:
        try:return json.loads(z.stdout[-3000:])
        except Exception:return None
    return None
targets=[('SYSTEM',sys.executable)]
for label,dir in (('NOX_VENV','/root/nox/.venv'),('NOX_TRAIN_VENV','/root/nox/venv'),
                  ('APP_VENV','/workspace/.venv'),('CONDA','/opt/conda')):
    p=Path(dir)/'bin/python'
    if p.exists() and p.is_file() and not p.is_symlink():
        targets.append((label,str(p)))
for label,python in targets:
    v=versions(python)
    if v:emit('PACKAGES',{'env':label,**v})
gpu=run(['nvidia-smi','--query-gpu=index,name,compute_cap,driver_version,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'])
if gpu and gpu.returncode==0:
    rows=[]
    for line in gpu.stdout.splitlines()[:2]:
        p=[x.strip() for x in line.split(',')]
        if len(p)==9 and p[0].isdigit() and all(re.fullmatch(r'[0-9.]+',v) for v in p[2:]):
            rows.append({'index':int(p[0]),'name':p[1],'compute_capability':p[2],
              'driver':p[3],'vram_total_mib':int(float(p[4])),'vram_free_mib':int(float(p[5])),
              'vram_used_mib':int(float(p[6])),'gpu_pct':int(float(p[7])),
              'gpu_temp_c':int(float(p[8]))})
    emit('GPUS',rows)
process=run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'])
if process and process.returncode==0:
    arr=[]
    for line in process.stdout.splitlines()[:30]:
        pieces=[s.strip() for s in line.split(',')]
        if len(pieces)==3 and pieces[1].isdigit():
            v=re.search(r'\d+',pieces[2])
            arr.append({'gpu_tail':pieces[0][-8:],'pid':int(pieces[1]),
                       'vram_mib':int(v.group()) if v else None})
    emit('GPU_PROCESSES',arr)
for tool in ('nvcc','nvidia-smi','numactl','gcc','cmake','ninja','uv','python3','zstd','pigz'):
    present=bool(shutil.which(tool))
    emit('BIN_TOOL',{'tool':tool,'available':present})
nvcc=run(['nvcc','--version'])
if nvcc and nvcc.returncode==0:
    match=re.search(r'release (\d+\.\d+)',nvcc.stdout)
    emit('CUDA_TOOLKIT',{'version':match.group(1) if match else 'UNKNOWN'})
cpu={}
cpu['cpus_available']=len(os.sched_getaffinity(0))
cpu['cpu_count']=os.cpu_count()
cpu['arch']=platform.machine()
cpu['numa_nodes']=len(list(Path('/sys/devices/system/node').glob('node[0-9]*')))
lscpu=run(['lscpu'])
if lscpu and lscpu.returncode==0:
    for line in lscpu.stdout.splitlines():
        if ':' not in line:continue
        k,v=[x.strip() for x in line.split(':',1)]
        if k in ('CPU(s)','Thread(s) per core','Core(s) per socket','Socket(s)',
                 'NUMA node(s)','Model name','L3 cache','Architecture'):
            cpu[k]=v[:110]
emit('CPU',cpu)
mem={}
for line in Path('/proc/meminfo').read_text().splitlines():
    if ':' not in line:continue
    name,value=line.split(':',1)
    if name in ('MemTotal','MemAvailable','Cached','SwapTotal','SwapFree','Shmem'):
        mem[name+'_bytes']=int(value.strip().split()[0])*1024
for label,mount in (('workspace','/workspace'),('tmpfs','/dev/shm')):
    try:
        v=os.statvfs(mount)
        mem[label+'_free_bytes']=v.f_bavail*v.f_frsize
        mem[label+'_total_bytes']=v.f_blocks*v.f_frsize
    except OSError:pass
emit('RAM_DISK',mem)

# Identify actual serving process + known tuning flags. Never export arbitrary
# argv or env (may contain tokens); allowlist of numeric/boolean flags only.
ports={}
ss=run(['ss','-H','-ltnp'])
if ss and ss.returncode==0:
    for line in ss.stdout.splitlines():
        p=re.search(r':(8080|8081)\s',line)
        proc=re.search(r'pid=(\d+)',line)
        if p and proc:ports[int(p.group(1))]=int(proc.group(1))
emit('MAIN_PORTS',{'proxy':8080 in ports,'llama':8081 in ports})
flags=('-c','--ctx-size','-np','--parallel','-t','--threads',
 '-tb','--threads-batch','-b','--batch-size','-ub','--ubatch-size',
 '-ngl','--n-gpu-layers','-ctk','--cache-type-k','-ctv','--cache-type-v',
 '-fa','--flash-attn','--split-mode','-sm','--cont-batching',
 '--no-cont-batching','--cache-reuse','-cram','--cache-ram',
 '--cache-idle-slots','--mmap','--mlock','-kvu','--kv-unified')
boolean_flags={'--cont-batching','--no-cont-batching','--cache-idle-slots',
 '--mmap','--mlock','-kvu','--kv-unified'}
if 8081 in ports:
    pid=ports[8081]
    try:
        parts=[s.decode('utf8','replace') for s in (Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0') if s]
        safe={}
        for i,key in enumerate(parts):
            if key not in flags:continue
            if key in boolean_flags:
                safe[key]=True
            elif i+1<len(parts) and re.fullmatch('[A-Za-z0-9_.:+-]{1,45}',parts[i+1]):
                safe[key]=parts[i+1]
        safe['cpu_affinity_count']=len(os.sched_getaffinity(pid))
        safe['nice']=os.getpriority(os.PRIO_PROCESS,pid)
        emit('LLAMA_FLAGS',safe)
    except (OSError,ValueError):emit('LLAMA_FLAGS',{'state':'HOLD_PROC'})
if 8080 in ports:
    try:
        pid=ports[8080]
        emit('PROXY_PROCESS',{'cpu_affinity_count':len(os.sched_getaffinity(pid)),
                              'nice':os.getpriority(os.PRIO_PROCESS,pid)})
    except OSError:pass

# Dedupe only via CPU metadata; no installation in this audit.
pkg=versions(sys.executable)
if pkg:
    installed=pkg.get('packages',{})
    candidate=('psutil','orjson','safetensors','huggingface-hub','hf-xet',
              'zstandard','rapidfuzz','watchdog','ninja','uv','faiss-cpu')
    emit('MISSING_CPU_TOOLKIT',[q for q in candidate if q not in installed])
print('NATIVE_V94_LIVE_MUTATIONS=false')
print('NATIVE_V94_NO_USER_CHAT_CONTENT_EXPORTED=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    ssh.REMOTE=REMOTE;ssh.api=settle
    buffer=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(buffer):
            ok=ssh.probe()
    except Exception as exc:
        s=str(exc)
        print('NOX_V94_HOLD='+s if s.startswith('HOLD_') and len(s)<110 else 'NATIVE_CONNECTOR')
    finally:
        try:
            with contextlib.redirect_stdout(buffer):
                if not ssh.cleanup():ok=False
        except Exception:
            ok=False
            print('NOX_V94_SSH_KEY_CLEANUP=HOLD')
    lines=buffer.getvalue().splitlines()
    for l in lines:
        if l.startswith(('NATIVE_V94_','TEMP_SSH_CLEANUP=')) and len(l)<2200:
            print(l)
    proof=any(s.startswith('NATIVE_V94_GPU') for s in lines)
    print('NOX_V94_NATIVE_INVENTORY_VERIFIED='+str(ok and proof).lower())
    return 0 if ok and proof else 2
if __name__=='__main__':raise SystemExit(main())
