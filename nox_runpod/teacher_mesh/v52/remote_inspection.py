"""NOX V52: zero-write, bounded native OneHost/S03/WEB/process inventory.

Reuses V51's previously accepted ephemeral SSH auth, direct Vast port, and
exact key detach procedure. Never exposes arbitrary shell from chat.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
import sys

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,subprocess,json,re,socket,hashlib
from pathlib import Path
def call(cmd,timeout=10):
    try:
        r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,timeout=timeout)
        return r.returncode,r.stdout[:25000]
    except (OSError,subprocess.TimeoutExpired):
        return 99,''
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V52_READ_ONLY_V1')
roots=[]
for parent in ('/root','/workspace','/app','/srv'):
    if not os.path.isdir(parent):continue
    try:
        for ent in os.scandir(parent):
            if ent.is_dir(follow_symlinks=False) and re.fullmatch('[A-Za-z0-9_.-]{1,90}',ent.name):
                if 'nox' in ent.name.lower() or 'onehost' in ent.name.lower():
                    roots.append(ent.path)
    except OSError:pass
print('NATIVE_PROJECT_ROOT_COUNT='+str(len(roots)))
for item in roots[:12]:
    print('NATIVE_PROJECT_ROOT='+item[:150])
# Bounded project-only traversal: don't follow links or scan secrets or model caches.
names={'onehost':[],'s03_db':[],'chat_html':[],'resonance_html':[],
       'checkpoint':[],'model':[],'dispatcher':[],'s03_module':[]}
seen=0
for project in roots[:12]:
    for base,subdirs,files in os.walk(project,followlinks=False):
        depth=len(Path(base).relative_to(project).parts)
        subdirs[:]=[n for n in subdirs if depth<5 and n not in
                    ('.git','.cache','.ssh','node_modules','venv','.venv',
                     '.tox','__pycache__','site-packages','huggingface')][:45]
        for f in files[:130]:
            seen+=1
            if seen>8000:break
            low=f.lower()
            full=Path(base)/f
            if not full.is_file() or full.is_symlink():continue
            try:size=full.stat().st_size
            except OSError:continue
            if 'onehost' in low:names['onehost'].append(full)
            if 's03' in low and low.endswith(('.sqlite','.sqlite3','.db')):
                names['s03_db'].append(full)
            elif low.endswith(('.db','.sqlite','.sqlite3')) and 'memory' in low:
                names['s03_db'].append(full)
            if low=='chat.html':names['chat_html'].append(full)
            if low=='resonance.html':names['resonance_html'].append(full)
            if low=='dispatcher.py':names['dispatcher'].append(full)
            if 's03' in low and low.endswith('.py'):names['s03_module'].append(full)
            if low.endswith(('.pt','.pth','.safetensors')) and size>1000000:
                names['checkpoint'].append(full)
            if low.endswith(('.gguf','.bin')) and size>100000000:
                names['model'].append(full)
        if seen>8000:break
    if seen>8000:break
print('NATIVE_PROJECT_FILES_SCANNED='+str(seen))
for key in names:
    print('NATIVE_FOUND_'+key.upper()+'_COUNT='+str(len(names[key])))
for key in ('onehost','s03_db','chat_html','resonance_html','dispatcher'):
    for p in names[key][:5]:
        # This is a project path, not file content or command arguments.
        print('NATIVE_CANDIDATE_'+key.upper()+'_PATH='+str(p)[:175])
for key in ('chat_html','resonance_html'):
    for p in names[key][:3]:
        try:
            if p.stat().st_size<=3000000:
                print('NATIVE_'+key.upper()+'_SHA256='+hashlib.sha256(p.read_bytes()).hexdigest())
        except OSError:pass
for port in (18775,18877,8000,8080,8888,5000,11434):
    try:
        with socket.create_connection(('127.0.0.1',port),timeout=0.6):
            val='true'
    except OSError:val='false'
    print('NATIVE_LOOPBACK_TCP_'+str(port)+'='+val)
rc,out=call(['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory',
             '--format=csv,noheader,nounits'])
if rc==0:
    apps=[]
    for line in out.splitlines()[:32]:
        fields=[p.strip() for p in line.split(',')]
        if len(fields)>=3 and fields[0].isdigit() and fields[-1].strip().isdigit():
            apps.append({'pid':int(fields[0]),'exe':Path(fields[1]).name[:50],
                         'vram_mb':int(fields[-1])})
    print('NATIVE_GPU_COMPUTE_PROCESSES_JSON='+json.dumps(apps,separators=(',',':')))
else: print('NATIVE_GPU_COMPUTE_PROCESSES=HOLD')
# Do not print command-line arguments, tokens, prompt bodies or environment.
counts={'nox':0,'onehost':0,'trainer':0,'forge':0,'llama':0,'web':0}
pids={k:[] for k in counts}
for d in os.listdir('/proc'):
    if not d.isdigit():continue
    try:
        cmd=(Path('/proc')/d/'cmdline').read_bytes()[:3000].replace(b'\0',b' ').lower()
    except OSError:continue
    for name in counts:
        if name.encode() in cmd:
            counts[name]+=1
            if len(pids[name])<12:pids[name].append(int(d))
print('NATIVE_NOX_PROCESS_CLASS_COUNTS='+json.dumps(counts,separators=(',',':')))
print('NATIVE_NOX_PROCESS_CLASS_SAMPLE_PIDS='+json.dumps(pids,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

if __name__=="__main__":
    connection.REMOTE=REMOTE
    ok=False
    try:
        ok=connection.probe()
    except Exception as exc:
        print("NOX_V52_AUDIT="+str(exc) if str(exc).startswith("HOLD_") else "NOX_V52_AUDIT=HOLD_NATIVE_INSPECT")
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:
            print("NOX_V52_CLEANUP=HOLD")
            ok=False
    raise SystemExit(0 if ok else 2)
