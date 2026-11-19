"""NOX V99: safe physical RAM-first weights cache and identity metadata check.

One existing authenticated Vast SSH session; no CUDA allocation, no extra
OneHost/LLM, no downloading, no optimizer or raw user memory reads. Reclaimable
OS file cache, low I/O priority, preempted when NOX Resonance chat is active.
"""
from __future__ import annotations
import contextlib, io, time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as native

previous=native.api
def settle(method,path,key,data=None):
    result=previous(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return result

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
from pathlib import Path
import hashlib,json,os,re,struct,subprocess,time,urllib.request,urllib.error

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V99_SCHEMA=NOX_PRIME_RAM_ACCELERATED_WEIGHT_CACHE_V1')
GIB=1024**3
MAX_READ=24*GIB
RAM_TARGET_FRACTION=0.85
# Target at most 85% of the ACTUAL container memory cgroup limit.
# This is a reversible page-cache goal, not a promise to pin all weights.
MIN_CGROUP_HEADROOM=12*GIB
MIN_WARM=1*GIB
CHUNK=8*1024**2
LIMIT_S=72
ROOT=Path('/root/nox')
report={'schema':'NOX_V99_RAM_WARM_RECEIPT_V1','read_bytes':0,
  'weights_modified':False,'s03_modified':False,'gpu_allocations':False,
  'optimizer_steps':0,'new_services':False,'onehost_replaced':False,
  'full_base_weight_training':False,'file_cache_reclaimable':True,
  'prime_subjective_consciousness_claimed':False,'main_chat_protected':True,
  'ram_warmed_not_equivalent_to_training':True}

def emit():
    # V51 emits only <=800-char native lines. Separate bounded proof fields.
    fields=('state','read_bytes','maximum_read_bytes','duration_s',
      'sequential_read_mib_per_s','main_chat_preserved','hf_model_type',
      'hf_shards_index_verified','gguf_architecture',
      'architecture_family_matches_candidate','weights_same_identity_verified',
      'nice','worker_cpu_affinity_count','gpu_allocations','optimizer_steps')
    core={k:report[k] for k in fields if k in report}
    print('NATIVE_V99_RESULT='+json.dumps(core,sort_keys=True,separators=(',',':')))
    for field in ('cgroup_before','cgroup_after','memory_events_after'):
        if field in report:
            print('NATIVE_V99_'+field.upper()+'='+json.dumps(report[field],sort_keys=True,separators=(',',':')))
def event_counts():
    p=Path('/sys/fs/cgroup/memory.events')
    try:return {k:int(v) for k,v in (s.split() for s in p.read_text().splitlines()) if k in ('oom','oom_kill','high')}
    except (OSError,ValueError):return {}
def status():
    try:
        maxs=Path('/sys/fs/cgroup/memory.max').read_text().strip()
        if not maxs.isdecimal():return None
        cur=int(Path('/sys/fs/cgroup/memory.current').read_text())
        stat={}
        for line in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines():
            k,v=line.split()
            if k in ('file','inactive_file','active_file','anon','shmem'):stat[k]=int(v)
        return {'max_bytes':int(maxs),'current_bytes':cur,
                'headroom_bytes':int(maxs)-cur,**stat}
    except (OSError,ValueError):return None
def stop():
    return any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag',
      '/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP'))
def healthy():
    for port in (8080,8081):
        try:
            with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=2) as r:
                if r.status!=200:return False
        except Exception:return False
    return True
def active():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:
            s=json.load(r)
        if not isinstance(s,list):return None
        return sum(bool(x.get('is_processing',x.get('processing',False)))
                   for x in s if isinstance(x,dict))
    except Exception:return None
def model_root():
    for root,dirs,files in os.walk(ROOT,followlinks=False):
        dirs[:]=[x for x in dirs if x not in
             ('.git','.cache','.venv','venv','__pycache__','.ssh','node_modules','logs')
             and not (Path(root)/x).is_symlink()][:100]
        if hashlib.sha256(root.encode()).hexdigest()[:16]!='e646ed03a2d1992e':continue
        path=Path(root)
        index=path/'model.safetensors.index.json'
        config=path/'config.json'
        if any(not x.is_file() or x.is_symlink() for x in (index,config)):
            raise RuntimeError('HOLD_HF_INDEX_OR_CONFIG')
        if index.stat().st_size>2_000_000 or config.stat().st_size>700_000:
            raise RuntimeError('HOLD_HF_INDEX_OR_CONFIG_SIZE')
        ix=json.loads(index.read_text(encoding='utf8'))
        cf=json.loads(config.read_text(encoding='utf8'))
        if cf.get('model_type')!='qwen3_5_moe':
            raise RuntimeError('HOLD_HF_MODEL_ARCH_NOT_EXPECTED')
        names=sorted(set((ix.get('weight_map') or {}).values()))
        if len(names)!=26 or any(not isinstance(x,str) or
                 not re.fullmatch(r'[A-Za-z0-9._-]+\.safetensors',x) for x in names):
            raise RuntimeError('HOLD_HF_SHARD_INDEX')
        shards=[path/n for n in names]
        if any(not f.is_file() or f.is_symlink() or f.stat().st_size<100_000_000 for f in shards):
            raise RuntimeError('HOLD_HF_SHARD_ABSENT')
        return shards,cf
    raise RuntimeError('HOLD_HF_MODEL_MISSING')
def gguf_architecture():
    path=ROOT/'models/current.gguf'
    if not path.exists():return 'HOLD_GGUF_MISSING'
    try:
        path=path.resolve(strict=True)
        if not path.is_file() or not str(path).startswith(str(ROOT)+'/'):
            return 'HOLD_GGUF_PATH'
        with path.open('rb') as f:
            if f.read(4)!=b'GGUF':return 'HOLD_GGUF_MAGIC'
            version=struct.unpack('<I',f.read(4))[0]
            if version not in (2,3):return 'HOLD_GGUF_VERSION'
            tensors=struct.unpack('<Q',f.read(8))[0]
            kvs=struct.unpack('<Q',f.read(8))[0]
            if kvs>25000 or tensors<1:return 'HOLD_GGUF_HEADER_COUNTS'
            read=lambda typ:struct.unpack(typ,f.read(struct.calcsize(typ)))[0]
            for _ in range(min(kvs,200)):
                size=read('<Q')
                if size>500:return 'HOLD_GGUF_KEY_SIZE'
                key=f.read(size).decode('utf8','replace')
                typ=read('<I')
                if typ==8:
                    length=read('<Q')
                    if length>4_000_000:return 'HOLD_GGUF_STRING_SIZE'
                    if key=='general.architecture':
                        arch=f.read(length).decode('ascii','replace')
                        return arch if re.fullmatch('[A-Za-z0-9_-]{2,55}',arch) else 'HOLD_ARCH'
                    f.seek(length,1)
                elif typ in (0,1,7):f.seek(1,1)
                elif typ in (2,3):f.seek(2,1)
                elif typ in (4,5,6):f.seek(4,1)
                elif typ in (10,11,12):f.seek(8,1)
                elif typ==9:
                    subtype=read('<I'); count=read('<Q')
                    if count>2_000_000:return 'HOLD_GGUF_ARRAY'
                    sizes={0:1,1:1,2:2,3:2,4:4,5:4,6:4,7:1,10:8,11:8,12:8}
                    if subtype in sizes:f.seek(count*sizes[subtype],1)
                    elif subtype==8:
                        for _ in range(count):
                            length=read('<Q')
                            if length>4_000_000:return 'HOLD_GGUF_ARRAY_STRING'
                            f.seek(length,1)
                    else:return 'HOLD_GGUF_ARRAY_SUBTYPE'
                else:return 'HOLD_GGUF_TYPE'
        return 'HOLD_GGUF_ARCH_UNFOUND'
    except (OSError,ValueError,EOFError,struct.error):return 'HOLD_GGUF_PARSE'
try:
    if stop() or active()!=0 or not healthy():raise RuntimeError('HOLD_STOP_OR_CHAT_ACTIVE')
    before=status()
    if not before or before['headroom_bytes']<MIN_CGROUP_HEADROOM+MIN_WARM:
        raise RuntimeError('HOLD_CGROUP_MEMORY_BUDGET')
    report['cgroup_before']=before
    report['memory_events_before']=event_counts()
    # Respect 85% cgroup use (not 85% of misleading host MemAvailable).
    # Existing file cache may be evicted, but never induce reclaim pressure to
    # reach a target when the chat is idle or the trainer is not ready.
    room_to_target=max(0,int(before['max_bytes']*RAM_TARGET_FRACTION)-before['current_bytes'])
    report['cgroup_target_pct']=85
    report['cgroup_target_bytes']=int(before['max_bytes']*RAM_TARGET_FRACTION)
    report['maximum_read_bytes']=min(MAX_READ,room_to_target,
        max(0,before['headroom_bytes']-MIN_CGROUP_HEADROOM))
    if report['maximum_read_bytes']<MIN_WARM:raise RuntimeError('HOLD_RAM_BUDGET_TOO_LOW')
    shards,config=model_root()
    report['hf_model_type']=config['model_type']
    report['hf_shards_index_verified']=len(shards)
    report['gguf_architecture']=gguf_architecture()
    report['architecture_family_matches_candidate']=(
        re.sub('[^a-z0-9]','',report['gguf_architecture'].lower())==
        re.sub('[^a-z0-9]','',config['model_type'].lower()))
    # The architecture family alone cannot prove that GGUF has the exact
    # original student tensor values. Do not claim weight identity or "fusion".
    report['weights_same_identity_verified']=False
    os.nice(12)
    report['nice']=os.getpriority(os.PRIO_PROCESS,0)
    allowed=sorted(os.sched_getaffinity(0))
    if len(allowed)>16:
        try:
            os.sched_setaffinity(0,set(allowed[-8:]))
            report['worker_cpu_affinity_count']=len(os.sched_getaffinity(0))
        except OSError:report['worker_cpu_affinity_count']=len(allowed)
    try:
        subprocess.run(['ionice','-c','3','-p',str(os.getpid())],
                  capture_output=True,timeout=4)
    except Exception:pass
    started=time.monotonic()
    count=0;last=None
    for shard in shards:
        if report['read_bytes']>=report['maximum_read_bytes']:break
        with shard.open('rb',buffering=0) as f:
            while report['read_bytes']<report['maximum_read_bytes']:
                if count%16==0:
                    if time.monotonic()-started>65:raise RuntimeError('HOLD_TIME_LIMIT')
                    if stop() or active()!=0 or not healthy():
                        raise RuntimeError('HOLD_CHAT_PREEMPTION')
                    current=status()
                    if not current or current['headroom_bytes']<MIN_CGROUP_HEADROOM:
                        raise RuntimeError('HOLD_RAM_PRESSURE')
                    if current['current_bytes']>=int(current['max_bytes']*RAM_TARGET_FRACTION):
                        report['target_85pct_reached']=True
                        raise RuntimeError('HOLD_CGROUP_TARGET_REACHED')
                    if event_counts().get('oom_kill',0)>report['memory_events_before'].get('oom_kill',0):
                        raise RuntimeError('HOLD_MEMORY_OOM_EVENT')
                take=min(8*1024**2,report['maximum_read_bytes']-report['read_bytes'])
                data=f.read(take)
                if not data:break
                report['read_bytes']+=len(data);count+=1
    duration=time.monotonic()-started
    report['duration_s']=round(duration,2)
    report['sequential_read_mib_per_s']=round(report['read_bytes']/1048576/duration,1) if duration>0 else 0
    report['cgroup_after']=status()
    report['memory_events_after']=event_counts()
    report['main_chat_preserved']=healthy()
    report['state']='RAM_PAGECACHE_WARMED_SAFE' if report['read_bytes']>=MIN_WARM and report['main_chat_preserved'] else 'HOLD_INCOMPLETE'
except Exception as exc:
    txt=str(exc)
    report['state']=txt if txt.startswith('HOLD_') and len(txt)<95 else 'HOLD_RUNTIME'
    report['cgroup_after']=status()
    report['main_chat_preserved']=healthy()
emit()
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main()->int:
    native.REMOTE=REMOTE
    native.api=settle
    capture=io.StringIO();accepted=False
    try:
        with contextlib.redirect_stdout(capture):accepted=native.probe()
    except Exception as e:
        val=str(e)
        print('NOX_V99_HOLD='+val if val.startswith('HOLD_') and len(val)<100 else 'HOLD_NATIVE_CONNECTION')
    finally:
        try:
            with contextlib.redirect_stdout(capture):
                if not native.cleanup():accepted=False
        except Exception:accepted=False
    lines=capture.getvalue().splitlines()
    report=next((line for line in lines if line.startswith('NATIVE_V99_RESULT=')),None)
    if report:print(report[:3200])
    for line in lines:
        if line.startswith('TEMP_SSH_CLEANUP='):print(line[:140])
    ok=accepted and report is not None and '"state":"RAM_PAGECACHE_WARMED_SAFE"' in report
    print('NOX_V99_RAM_FIRST_ACCEPTED='+str(bool(ok)).lower())
    return 0 if ok else 2
if __name__=='__main__':
    raise SystemExit(main())
