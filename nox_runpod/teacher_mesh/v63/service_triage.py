"""NOX V63: bounded native service triage through established V51 ephemeral SSH.

Read-only: no service starts/stops, file mutation, model selection, downloads,
GPU training, or secrets/log text export. Uses the same authorized Vast route.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
import time

# Keep the shared V51 transport unchanged. Applied only to this read-only probe:
# Vast SSH key attachment can succeed before sshd starts honoring the key.
_v51_api = connection.api
def _v63_delayed_attach(method,path,key,data=None):
    receipt=_v51_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(12)
    return receipt

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,shutil,hashlib,subprocess,json,socket,time
from pathlib import Path
SERVICES=(
 'nox-agent-tuner-t858u','nox-downloads-t802u','nox-teacher-bringup',
 'nox-teacher-serve-t811u','nox-train-worm-t811u'
)
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_SERVICE_TRIAGE_V1')

def run(args,timeout=7):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
        return p.returncode,p.stdout[:70000],p.stderr[:5000]
    except (OSError,subprocess.TimeoutExpired) as e:
        return -1,'',type(e).__name__

signals={
 'disk_full':r'no space left on device|enospc|disk quota exceeded',
 'oom_gpu':r'cuda out of memory|cublas_status_alloc_failed|outofmemoryerror',
 'oom_ram':r'memoryerror|oom.kill|out of memory|killed process',
 'cuda_version':r'unsupported.*sm_70|cuda error|no kernel image|unsupported gpu architecture',
 'missing_path':r'no such file or directory|filenotfounderror|model file does not exist',
 'missing_dependency':r'modulenotfounderror|importerror|command not found',
 'network':r'connection refused|network is unreachable|temporary failure in name resolution|connection reset',
 'auth':r'401 unauthorized|403 forbidden|authentication failed|access denied|permission denied',
 'port_in_use':r'address already in use|eaddrinuse',
 'normal_finish':r'completed successfully|training complete|finished normally|exit code 0',
 'interrupted':r'sigterm|keyboardinterrupt|received stop|graceful shutdown',
 'checkpoint':r'checkpoint saved|optimizer state saved|saving checkpoint',
 'model_load':r'loading model|model load|model weights',
}

def classify(blob):
    lower=blob.lower()
    return {k:bool(re.search(v,lower,re.I)) for k,v in signals.items()}

def parse_status(blob):
    out={}
    for line in blob.splitlines()[:350]:
        parts=line.strip().split()
        if len(parts)<2:continue
        key=parts[0].split(':')[-1]
        if key in SERVICES and re.fullmatch(r'[A-Z_]+',parts[1]):
            out[key]=parts[1]
    return out

supervisorctl=shutil.which('supervisorctl')
supervisord=shutil.which('supervisord')
configs=[
 '/etc/supervisor/supervisord.conf',
 '/etc/supervisord.conf',
 '/root/nox/supervisord.conf',
 '/root/nox/config/supervisord.conf',
 '/root/nox/supervisor/supervisord.conf',
]
variants=[]
if supervisorctl:
    variants.append([supervisorctl,'status'])
    for c in configs:
        if os.path.isfile(c):
            variants.append([supervisorctl,'-c',c,'status'])
known={}
supervisor_available=False
supervisor_variant=None
for idx,args in enumerate(variants[:7]):
    rc,out,err=run(args,timeout=8)
    observed=parse_status(out)
    if observed:
        known.update(observed)
        supervisor_available=True
        supervisor_variant=idx
        break
print('NATIVE_SUPERVISORCTL_PRESENT='+str(bool(supervisorctl)).lower())
print('NATIVE_SUPERVISORD_PRESENT='+str(bool(supervisord)).lower())
print('NATIVE_SUPERVISOR_STATUS_READABLE='+str(supervisor_available).lower())
print('NATIVE_SUPERVISOR_STATUS_VARIANT='+str(supervisor_variant))

# Look up relevant program names and selected log files without reading their
# command, environment, user data, passwords, or arbitrary outside paths.
config_hits={service:[] for service in SERVICES}
candidate_dirs=('/etc/supervisor','/root/nox/program','/root/nox/supervisor','/root/nox/services','/root/nox/config')
files_examined=0
for parent in candidate_dirs:
    if not os.path.isdir(parent):continue
    for root,dirs,files in os.walk(parent,followlinks=False):
        depth=len(Path(root).relative_to(parent).parts)
        dirs[:]=[d for d in dirs if depth<4 and d not in (
            '.git','.ssh','.cache','models','checkpoints','weights','node_modules','venv','.venv','__pycache__'
        )][:40]
        for name in files[:130]:
            if not name.lower().endswith(('.conf','.ini','.service','.yaml','.yml','.json','.toml','.py')):
                continue
            file=Path(root)/name
            try:
                if file.is_symlink() or file.stat().st_size>180000:continue
                raw=file.read_bytes()
            except OSError:continue
            files_examined+=1
            for service in SERVICES:
                if service.encode() in raw and len(config_hits[service])<6:
                    config_hits[service].append({
                        'path':str(file)[:170],
                        'sha256':hashlib.sha256(raw).hexdigest(),
                    })
            if files_examined>=1200:break
        if files_examined>=1200:break
    if files_examined>=1200:break
print('NATIVE_SERVICE_CONFIG_FILES_SCANNED='+str(files_examined))

# No raw supervisor logs are allowed to leave the host. Return only anomaly
# classifications and a digest of the last 48k bytes for reproducibility.
def tail_from_supervisor(service):
    if not supervisorctl:return None,'unavailable'
    command=[supervisorctl,'tail','-20000',service,'stderr']
    rc,out,err=run(command,timeout=8)
    if rc==0 and out:
        return out.encode('utf-8',errors='replace')[:48000],'supervisorctl'
    # supervisorctl tail might use "-20000" as an invalid option, use last 200 lines
    rc,out,err=run([supervisorctl,'tail',service,'stderr'],timeout=8)
    if rc==0 and out:return out.encode('utf-8',errors='replace')[:48000],'supervisorctl'
    return None,'not_readable'

def proc_hits(service):
    hits=[]
    for item in os.listdir('/proc'):
        if not item.isdigit():continue
        try:
            cmd=(Path('/proc')/item/'cmdline').read_bytes()[:3000]
            if service.encode() not in cmd:continue
            comm=(Path('/proc')/item/'comm').read_text().strip()
            hits.append({'pid':int(item),'comm':comm[:36]})
        except (OSError,UnicodeError):continue
        if len(hits)>=8:break
    return hits

for service in SERVICES:
    log,log_source=tail_from_supervisor(service)
    result={
        'service':service,
        'supervisor_state':known.get(service,'UNKNOWN'),
        'config_file_count':len(config_hits[service]),
        'config_first':config_hits[service][0]['path'][:100] if config_hits[service] else None,
        'config_sha256':config_hits[service][0]['sha256'] if config_hits[service] else None,
        'matching_pids':[p['pid'] for p in proc_hits(service)][:6],
        'log_source':log_source,
        'log_sha256':hashlib.sha256(log).hexdigest() if log else None,
        'error_signals':[k for k,v in classify(log.decode('utf-8',errors='replace')).items() if v] if log else [],
        'log_readable':bool(log),
    }
    print('NATIVE_SERVICE_TRIAGE='+json.dumps(result,ensure_ascii=False,separators=(',',':')))

def health(port):
    import urllib.request,urllib.error
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=1.5) as r:
            return r.status
    except urllib.error.HTTPError as e:return e.code
    except (OSError,urllib.error.URLError):return None

free=None
try:free=shutil.disk_usage('/workspace').free
except OSError:pass
ram_available=None
try:
    for row in Path('/proc/meminfo').read_text().splitlines():
        if row.startswith('MemAvailable:'):
            ram_available=int(row.split()[1])*1024
            break
except (OSError,ValueError):pass
gpu=run(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'],timeout=10)
gpu_rows=[]
for line in gpu[1].splitlines()[:3]:
    f=[p.strip() for p in line.split(',')]
    if len(f)==4 and all(v.isdigit() for v in f):gpu_rows.append([int(v) for v in f])
resource={'disk_free_bytes':free,'ram_available_bytes':ram_available,
    'gpus_used_mb_util_pct_temp_c':gpu_rows,
    'health_http_8080':health(8080),'health_http_8081':health(8081),
    'supervisor_readable':supervisor_available,'source':'native_ssh'}
print('NATIVE_SERVICE_RESOURCES='+json.dumps(resource,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main() -> int:
    connection.REMOTE=REMOTE
    connection.api=_v63_delayed_attach
    ok=False
    try:
        ok=connection.probe()
    except Exception as e:
        print("NOX_V63_HOLD="+str(e)[:100] if str(e).startswith("HOLD_") else "NOX_V63_HOLD=TRIAGE_EXCEPTION")
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:
            print("NOX_V63_HOLD=SSH_CLEANUP_UNVERIFIED")
            ok=False
    print("NOX_V63_SERVICE_STATE_READONLY="+str(ok).lower())
    return 0 if ok else 2

if __name__=="__main__":
    raise SystemExit(main())
