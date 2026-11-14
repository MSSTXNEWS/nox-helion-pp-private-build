"""NOX V95: physically warm verified HF model weight pages into OS RAM cache.

One short-lived CPU-only task, executed by existing V51 authorized SSH.
Page cache (not /dev/shm) is reclaimable, unlike copying 67GiB BF16 weights
into fixed shm and starving the main chat. No optimizer, GPU, downloads,
deletions, extra service, main model or S03 changes.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as bridge
_before=bridge.api
def settle(method,path,key,data=None):
    result=_before(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return result

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib,json,os,re,subprocess,sys,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V95_RAM_WARM_SCHEMA=NOX_WEIGHT_PAGECACHE_WARMUP_V1')
MAX_BYTES=2*1024**3
READ_CHUNK=8*1024**2
MAX_DURATION_S=65
PER_FILE_CAP=1*1024**3
MIN_CGROUP_UNUSED=6*1024**3
LOW_PRIORITY=10

def stop():
    return any(Path(p).exists() for p in (
        '/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
        '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP'))

def health(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:
            return r.status
    except Exception:return None

def slots():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8081/slots',timeout=3) as r:
            d=json.load(r)
        if not isinstance(d,list):return None
        return sum(bool(row.get('is_processing')) for row in d if isinstance(row,dict))
    except Exception:return None

def cgroup():
    try:
        m=Path('/sys/fs/cgroup/memory.max').read_text().strip()
        c=int(Path('/sys/fs/cgroup/memory.current').read_text().strip())
        if not m.isdigit():return None
        mx=int(m)
        stats={}
        for line in Path('/sys/fs/cgroup/memory.stat').read_text().splitlines():
            k,v=line.split()
            if k in ('anon','file','active_file','inactive_file','shmem'):
                stats[k]=int(v)
        return {'max':mx,'current':c,'headroom':mx-c,**stats}
    except Exception:return None

def root_model():
    for parent,dirs,files in os.walk('/root/nox',followlinks=False):
        dirs[:]=[d for d in dirs if d not in (
           '.git','.cache','logs','node_modules','venv','.venv','__pycache__','.ssh')
           and not (Path(parent)/d).is_symlink()][:100]
        if hashlib.sha256(parent.encode()).hexdigest()[:16]!='e646ed03a2d1992e':
            continue
        path=Path(parent)
        index=path/'model.safetensors.index.json'
        if not index.is_file() or index.is_symlink() or index.stat().st_size>2_000_000:
            raise RuntimeError('HOLD_SOURCE_INDEX')
        mapping=json.loads(index.read_text())
        names=sorted(set((mapping.get('weight_map') or {}).values()))
        if len(names)!=26 or any(not re.fullmatch(r'[A-Za-z0-9._-]+\.safetensors',n) for n in names):
            raise RuntimeError('HOLD_SHARDS_MISMATCH')
        paths=[path/name for name in names]
        if any(not p.is_file() or p.is_symlink() or p.stat().st_size<100_000_000 for p in paths):
            raise RuntimeError('HOLD_SHARD_MISSING')
        return paths
    raise RuntimeError('HOLD_QWEN_HF_SOURCE_NOT_FOUND')

report={'state':'HOLD','source':'QWEN35_HF_MOE26','bytes_read':0,
        'size_limit_bytes':MAX_BYTES,'model_files_modified':False,
        'gpu_allocations':False,'no_training_started':True,'main_chat_preserved':False,
        'background_priority_nice':None,'trusted_full_model_hash_checked':False,
        'pagecache_advisory':True,'offsite_backup_untouched':True}
def emit():
    print('NATIVE_V95_RAM_WARM='+json.dumps(report,sort_keys=True,separators=(',',':')))

try:
    if stop():raise RuntimeError('HOLD_STOP')
    if slots()!=0:raise RuntimeError('HOLD_CHAT_ACTIVE_OR_UNKNOWN')
    if health(8080)!=200 or health(8081)!=200:raise RuntimeError('HOLD_CHAT_HEALTH')
    cg=cgroup()
    if cg is None or cg['headroom']<MIN_CGROUP_UNUSED:
        raise RuntimeError('HOLD_CGROUP_HEADROOM')
    report['cgroup_headroom_before_bytes']=cg['headroom']
    report['cgroup_cached_before_bytes']=cg.get('file')
    report['cgroup_inactive_file_before_bytes']=cg.get('inactive_file')
    try:os.nice(LOW_PRIORITY)
    except OSError:pass
    report['background_priority_nice']=os.getpriority(os.PRIO_PROCESS,0)
    try:
        if subprocess.run(['which','ionice'],capture_output=True,timeout=3).returncode==0:
            subprocess.run(['ionice','-c','3','-p',str(os.getpid())],
                capture_output=True,timeout=3)
    except Exception:pass
    paths=root_model()
    report['shards_verified_by_index']=len(paths)
    start=time.monotonic()
    calls=0
    for path in paths[:2]:
        written_this=0
        with path.open('rb',buffering=0) as f:
            if hasattr(os,'posix_fadvise') and hasattr(os,'POSIX_FADV_WILLNEED'):
                try:os.posix_fadvise(f.fileno(),0,PER_FILE_CAP,os.POSIX_FADV_WILLNEED)
                except OSError:pass
            while written_this<PER_FILE_CAP and report['bytes_read']<MAX_BYTES:
                if time.monotonic()-start>MAX_DURATION_S:
                    report['state']='HOLD_TIME_BUDGET';break
                if calls%8==0:
                    if stop() or slots()!=0 or health(8080)!=200 or health(8081)!=200:
                        report['state']='HOLD_CHAT_OR_STOP_PREEMPTED';break
                    now=cgroup()
                    if now is None or now['headroom']<MIN_CGROUP_UNUSED:
                        report['state']='HOLD_CGROUP_HEADROOM_AFTER_WARM';break
                block=f.read(min(READ_CHUNK,PER_FILE_CAP-written_this))
                if not block:break
                written_this+=len(block)
                report['bytes_read']+=len(block)
                calls+=1
            if report['state'].startswith('HOLD_') and report['state']!='HOLD':
                break
    elapsed=time.monotonic()-start
    now=cgroup()
    report['duration_s']=round(elapsed,3)
    report['throughput_mib_s']=round(report['bytes_read']/1048576/elapsed,2) if elapsed else 0
    report['cgroup_headroom_after_bytes']=now['headroom'] if now else None
    report['cgroup_cached_after_bytes']=now.get('file') if now else None
    report['cgroup_inactive_file_after_bytes']=now.get('inactive_file') if now else None
    report['main_chat_preserved']=health(8080)==200 and health(8081)==200
    if report['state']=='HOLD' and report['bytes_read']==MAX_BYTES and report['main_chat_preserved']:
        report['state']='RAM_WEIGHT_PAGECACHE_WARMED'
    elif report['state']=='HOLD':
        report['state']='HOLD_PARTIAL_PAGECACHE'
except Exception as ex:
    reason=str(ex)
    report['state']=reason if reason.startswith('HOLD_') and len(reason)<100 else 'HOLD_RAM_WARM_EXCEPTION'
    report['main_chat_preserved']=health(8080)==200 and health(8081)==200
emit()
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main()->int:
    bridge.REMOTE=REMOTE
    bridge.api=settle
    stdout=io.StringIO()
    ok=False
    try:
        with contextlib.redirect_stdout(stdout):ok=bridge.probe()
    except Exception as e:
        msg=str(e)
        print('NOX_V95_RAM_WARM_HOLD='+msg if msg.startswith('HOLD_') and len(msg)<80 else 'NOX_V95_RAM_WARM_HOLD=NATIVE_CONNECTOR')
    finally:
        try:
            with contextlib.redirect_stdout(stdout):
                if not bridge.cleanup():ok=False
        except Exception:ok=False
    line=next((s for s in stdout.getvalue().splitlines() if s.startswith('NATIVE_V95_RAM_WARM=')),None)
    if line and len(line)<1700:
        print(line)
    for s in stdout.getvalue().splitlines():
        if s.startswith('TEMP_SSH_CLEANUP='):print(s[:120])
    status=line and 'RAM_WEIGHT_PAGECACHE_WARMED' in line
    print('NOX_V95_RAM_WEIGHT_WARM_VERIFIED='+str(bool(ok and status)).lower())
    return 0 if ok and status else 2
if __name__=='__main__':
    raise SystemExit(main())
