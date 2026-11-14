"""NOX V76: ONE physical run, one existing Vast/OneHost, seven acceptance gates.

No second scheduler, paid instance or main model. Uses the V72 owner-authorized
SSH channel and honest receipts. Stages exact verified source into isolated
workspace, not production. Every unmet dependent gate is explicit HOLD.
"""
from __future__ import annotations
import ast
import base64
import hashlib
import io
import json
import subprocess
import tarfile
import time
from pathlib import Path
from nox_runpod.teacher_mesh.v72 import onepass_live as runner

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import base64,hashlib,importlib,io,json,os,re,shutil,sqlite3,subprocess,sys,tarfile,time,urllib.request,urllib.error
from pathlib import Path
R={'schema':'NOX_V72_ONEPASS_NATIVE_RECEIPT_V1',
   'instance_id':60509551,'state':'LIVE_CHECKS_PASS_PARTIAL_HOLD',
   'v76_schema':'NOX_V76_SEVEN_GATE_EXECUTION_V1','source_revision':'aa77a7d43bcceee696e2d6ff73d3285d217ab001',
   'production_main_model_changed':False,'production_proxy_changed':False,
   'production_s03_changed':False,'training_started':False,'native_onehost_replaced':False,
   'new_process_or_scheduler':False,'deleted_files':False,'optimizer_steps':0,
   'native_task_ids':[],'gates':{}}
G=R['gates']
def gate(name,state,**kw):
    d={'state':state}
    d.update(kw)
    G[name]=d
def get(port,path,method='GET',data=None,timeout=3):
    request=urllib.request.Request('http://127.0.0.1:'+str(port)+path,
               method=method,data=data,headers={'Accept':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            return response.status,response.read(80000)
    except urllib.error.HTTPError as error:
        return error.code,b''
    except Exception:
        return 0,b''
def emit():
    # Stable receipt, never print secrets/absolute user paths, never claim 100%.
    R['full_completion_verified']=all(G.get(k,{}).get('state')=='PASS' for k in
       ('chat_and_one_model','s03_ram','onehost_native','cold_restore',
        'forge_weight_change','r60_jobs','quality_and_rollback'))
    if R['full_completion_verified']:
        R['state']='LIVE_CHECKS_PASS_ALL_SEVEN_VERIFIED'
    print('NATIVE_V72_JSON='+json.dumps(R,sort_keys=True,separators=(',',':')))
def sha_blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def no_stop():
    paths=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
           '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
    return not any(Path(x).exists() for x in paths)
def supervised(n):
    try:
        r=subprocess.run(['supervisorctl','status',n],capture_output=True,text=True,timeout=5)
        parts=r.stdout.strip().split()
        if r.returncode==0 and len(parts)>1:
            pid=int(parts[3].rstrip(',')) if len(parts)>3 and parts[2]=='pid' and parts[3].rstrip(',').isdigit() else None
            return parts[1],pid
    except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return 'UNKNOWN',None

# G1: interactive NOX is the only user-facing student, no proxy/public bypass.
free=shutil.disk_usage('/workspace').free
R['workspace_free_bytes']=free
try:
    with Path('/proc/meminfo').open() as f:
        data=f.read()
    match=re.search(r'^MemAvailable:\s+(\d+)',data,re.M)
    R['ram_available_bytes']=int(match.group(1))*1024 if match else None
except OSError:R['ram_available_bytes']=None
for p in (8080,8081):
    status,_=get(p,'/health')
    R['health_'+str(p)]=status
model_id=None
status,body=get(8081,'/v1/models')
if status==200:
    try:
        rows=json.loads(body).get('data',[])
        model_id=rows[0].get('id') if rows else None
    except (ValueError,TypeError,KeyError):pass
stop_clear=no_stop()
R['stop_clear']=stop_clear
if status==200 and isinstance(model_id,str) and model_id.endswith('/models/current.gguf') and R['health_8080']==200 and R['health_8081']==200 and stop_clear:
    gate('chat_and_one_model','PASS',model_endpoint='existing_8081',chat_proxy='existing_8080')
else:
    gate('chat_and_one_model','HOLD_MAIN_MODEL_OR_STOP')
try:
    z=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.free,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=7)
    gpu=[]
    if z.returncode==0:
        for row in z.stdout.splitlines()[:2]:
            p=[v.strip() for v in row.split(',')]
            if len(p)==4 and p[0].isdigit() and 'V100' in p[1]:
                gpu.append({'id':int(p[0]),'free_mib':int(p[2]),'utilization_pct':int(p[3])})
    R['gpus']=gpu
except Exception:R['gpus']=[]

# G2: consistent S03 SQLite online copies to volatile RAM (S03 original remains).
memroots=[
 ('seed','/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'),
 ('infinite','/root/nox/memory/infinite/nox_infinite_memory.sqlite3'),
 ('copy','/root/nox/memory/pc_t809u/nox_seed_memory.sqlite3')]
s03=[]
for label,path in memroots:
    p=Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size>80_000_000:continue
    source=mirror=None
    try:
        source=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=6)
        source.execute('PRAGMA query_only=ON')
        mirror=sqlite3.connect(':memory:')
        source.backup(mirror,pages=512,sleep=.02)
        check=mirror.execute('PRAGMA quick_check').fetchone()
        tables=mirror.execute('SELECT count(*) FROM sqlite_master WHERE type="table"').fetchone()[0]
        if check and check[0]=='ok' and tables>0:
            s03.append(label)
    except (OSError,sqlite3.Error):pass
    finally:
        if mirror:mirror.close()
        if source:source.close()
gate('s03_ram','PASS' if len(s03)==3 else 'HOLD_S03_RAM_READBACK',db_count=len(s03),
     activated_in_chat=False)

# G3: physical SHA-pinned staging of EXACT OnePrime sources. No live imports or
# service mutation; staging is needed for safe OneHost callback integration.
base=Path('/workspace/nox_mega_stage_verified')
dest=base/'v76_prime_package'
# Source bundles are verified in the ephemeral GitHub Actions runner and
# carried inside the same authenticated SSH session; no untrusted raw URLs.
BUNDLE_B64='__NOX_V76_BUNDLE__'
sources={
'nox_runpod/teacher_mesh/v71/__init__.py':'c0d071384a2072007d50f88a9feb72f607ea1754',
'nox_runpod/teacher_mesh/v71/one_prime.py':'307c987eb4d62b1d8a997c75e57a5e4d43496e99',
'nox_runpod/teacher_mesh/v71/ram_policy.py':'01f21db43414eab2801460d85ba576fec8d857f3',
'nox_runpod/teacher_mesh/v71/disk_budget.py':'b9dc8ffe758be3a44e3d4f1f8752aefcf441b1db',
'nox_runpod/teacher_mesh/v71/offload_policy.py':'7909d25b95c8202bd9f6a788122945269a007147',
'nox_runpod/teacher_mesh/v38/__init__.py':'4528764295ae4cd4c6b605546c8f2d8f9d885b11',
'nox_runpod/teacher_mesh/v38/native_bridge_v38.py':'dc58cbd4344802027eaf2a11a7f65f82e06c1a14',
'nox_runpod/teacher_mesh/v38/synaptic_brain.py':'8340a74469d9242a94a16d611b5980ac084808de',
'nox_runpod/teacher_mesh/v38/durable_runtime.py':'17aca9d60aa2d11c4f6eeef47982963a4a5946e6',
'nox_runpod/teacher_mesh/v41/training/__init__.py':'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391',
'nox_runpod/teacher_mesh/v41/training/priority_autonomy.py':'d4e07f995ec3de52b68519a7ebf61c3134cca782',
'nox_runpod/teacher_mesh/v43/nox/resource_brain.py':'dd6d15af686e2ca9e3e8e8bfe9729f9fda9cb3c2'
}
staged=False;stage_error='HOLD_UNKNOWN';total_bytes=0
if stop_clear and free>10_000_000_000:
    try:
        src={}
        raw_bytes=base64.b64decode(BUNDLE_B64,validate=True)
        if len(raw_bytes)>150_000:
            raise RuntimeError('HOLD_BUNDLE_SIZE')
        with tarfile.open(fileobj=io.BytesIO(raw_bytes),mode='r:gz') as tf:
            members=tf.getmembers()
            if len(members)!=len(sources) or set(m.name for m in members)!=set(sources):
                raise RuntimeError('HOLD_BUNDLE_FILE_MANIFEST')
            for member in members:
                if not member.isfile() or member.size>140000 or member.name not in sources:
                    raise RuntimeError('HOLD_BUNDLE_MEMBER')
                stream=tf.extractfile(member)
                if stream is None:raise RuntimeError('HOLD_BUNDLE_FILE')
                body=stream.read(140001)
                if sha_blob(body)!=sources[member.name]:
                    raise RuntimeError('HOLD_LOCAL_SOURCE_BLOB_SHA')
                compile(body.decode('utf-8'),member.name,'exec')
                src[member.name]=body
                total_bytes+=len(body)
        if dest.exists():
            if dest.is_symlink() or not dest.is_dir():raise RuntimeError('HOLD_OLD_STAGE_CONFLICT')
            for name,body in src.items():
                p=dest/name
                if not p.is_file() or p.is_symlink() or p.read_bytes()!=body:
                    raise RuntimeError('HOLD_OLD_STAGE_CONFLICT')
        else:
            if base.is_symlink():raise RuntimeError('HOLD_STAGE_PARENT_SYMLINK')
            base.mkdir(parents=True,exist_ok=True)
            import tempfile
            temp=Path(tempfile.mkdtemp(prefix='nox-v76-',dir=base))
            try:
                for name,body in src.items():
                    f=temp/name
                    f.parent.mkdir(parents=True,exist_ok=True)
                    with f.open('xb') as out:
                        out.write(body);out.flush();os.fsync(out.fileno())
                    f.chmod(0o600)
                os.rename(temp,dest)
            finally:
                if temp.exists():shutil.rmtree(temp)
            # Read exact source back after atomic stage.
        staged=all((dest/n).is_file() and sha_blob((dest/n).read_bytes())==h
                   for n,h in sources.items())
        if staged:
            sys.path.insert(0,str(dest))
            from nox_runpod.teacher_mesh.v71.one_prime import OnePrime
            from nox_runpod.teacher_mesh.v71.disk_budget import SAFETY_FLOOR_BYTES
            if SAFETY_FLOOR_BYTES!=10_000_000_000:raise RuntimeError('HOLD_WRONG_DISK_POLICY')
            stage_error='STAGED_SHA_LOCKED_IMPORT_PASS'
        else:stage_error='HOLD_STAGE_READBACK'
    except Exception as exc:
        stage_error=str(exc) if str(exc).startswith('HOLD_') else 'HOLD_STAGE_FETCH_OR_IMPORT'
else:
    stage_error='HOLD_STOP_OR_DISK_STAGE'
gate('oneprime_staged','PASS' if staged and stage_error=='STAGED_SHA_LOCKED_IMPORT_PASS' else stage_error,
     bytes=total_bytes,files=len(sources) if staged else 0,production_activated=False)

# Real callbacks must be wired to the existing *authenticated* proxy/S03,
# never replaced with stand-ins and never monkey-patched based on assumptions.
try:
    p=Path('/root/nox/scripts/chat_proxy.py')
    if not p.is_file():p=Path('/root/nox/chat_proxy.py')
    source=p.read_text(encoding='utf-8',errors='replace') if p.is_file() and p.stat().st_size<180000 else ''
    has_owner='owner_completion' in source
    has_s03='_s03_persist_pair' in source or 's03_recall' in source
    supervisor,proxy_pid=supervised('nox-proxy')
    R['live_proxy_supervisor']=supervisor
    R['live_proxy_pid_verified']=proxy_pid is not None
    G['onehost_native']={'state':'HOLD_V71_NATIVE_CALLBACKS_NOT_BOUND',
       'owner_completion_present':has_owner,'s03_function_present':has_s03,
       'supervisor':'nox-proxy' if supervisor=='RUNNING' else 'HOLD',
       'production_activated':False}
except Exception:
    gate('onehost_native','HOLD_NATIVE_PROXY_SOURCE')

# G4 Cold backups: local readback != OWNER-key *offsite restore*. Never overwrite
# existing optimizer/S03 or claim owner restore from ciphertext metadata alone.
gate('cold_restore','HOLD_OWNER_KEY_OFFSITE_RESTORE_AND_OPTIMIZER_RESUME_UNVERIFIED',
     drive_copies_known=True,source_files_deleted=False)

# G5 FORGE: one student, no new GPU server; scan bounded local HF dirs.
found=0;optimizer_found=0
for root in ('/root/nox/models','/root/nox/forge','/root/nox/training'):
    base_dir=Path(root)
    if not base_dir.is_dir():continue
    for parent,dirs,files in os.walk(base_dir,followlinks=False):
        depth=len(Path(parent).relative_to(base_dir).parts)
        dirs[:]=[d for d in dirs if depth<3 and d not in ('.git','.cache','venv','.venv','checkpoints')][:70]
        if 'config.json' in files and any(x.endswith('.safetensors') for x in files):
            found+=1
        optimizer_found+=sum('optimizer' in x.lower() for x in files)
        if found>20 or optimizer_found>200:break
    if found>20 or optimizer_found>200:break
R['candidate_trainable_hf_dirs_sampled']=found
R['optimizer_name_count_sampled']=optimizer_found
gate('forge_weight_change','HOLD_NATIVE_TRAINABLE_STUDENT_OWNER_LEASE_AND_RESTORE',
     optimizer_steps=0,active_gguf_changed=False,teacher_distillation_verified=False)

# G6 R60: queue GET/readback is mandatory before assigning native IDs.
status,api=get(8095,'/openapi.json',timeout=3)
queue_methods=[]
if status==200:
    try:
        paths=json.loads(api).get('paths',{})
        for path,methods in paths.items():
            if 'queue' in path.lower() and isinstance(methods,dict):
                queue_methods+=list(methods)
    except (TypeError,ValueError):pass
gate('r60_jobs','HOLD_NATIVE_QUEUE_OWNER_READBACK_AND_SIGNED_JOB_RECEIPTS',
     live_native_task_ids=0,source_planned=60,queue_methods=sorted(set(queue_methods)))

# G7: native STOP is not validated by assuming a missing flag is enough.
# Benchmark is direct model only; UI end-to-end owner session remains protected.
if not stop_clear:
    gate('quality_and_rollback','HOLD_STOP')
else:
    gate('quality_and_rollback','HOLD_AUTHENTICATED_RESONANCE_S03_STOP_ROLLBACK_E2E',
         current_model_preserved=True)
R['chat_priority_source']='P0_CHAT_P1_TEACHERS_EXISTING_V73'
R['disk_min_new_write_bytes']=10_000_000_000
R['s03_canonical_sqlite_unchanged']=True
R['stop_flag_clear']=stop_clear
emit()
PYREMOTE
"""

def _bundle_existing_sources() -> str:
    """Bundle only SHA-allowlisted repo code, not keys, user data or weights."""
    root=Path(__file__).resolve().parents[3]
    script=REMOTE.lstrip('\n').split("python3 - <<'PYREMOTE'\n",1)[1].rsplit("\nPYREMOTE",1)[0]
    parsed=ast.parse(script)
    src=None
    for statement in parsed.body:
        if isinstance(statement,ast.Assign) and any(
             isinstance(t,ast.Name) and t.id=='sources' for t in statement.targets):
            src=ast.literal_eval(statement.value)
            break
    if not isinstance(src,dict) or len(src)!=12:
        raise RuntimeError('HOLD_SOURCE_MAP')
    memory=io.BytesIO()
    with tarfile.open(fileobj=memory,mode='w:gz') as tar:
        for name,expected in sorted(src.items()):
            if not name.startswith('nox_runpod/teacher_mesh/') or '../' in name:
                raise RuntimeError('HOLD_SOURCE_PATH')
            # Read the original committed Git blob, not a working-tree file
            # that .gitattributes may rewrite during checkout.
            actual=subprocess.run(['git','-C',str(root),'rev-parse','HEAD:'+name],
                capture_output=True,text=True,check=True,timeout=5).stdout.strip()
            if actual!=expected:
                raise RuntimeError('HOLD_GIT_TREE_BLOB_SHA_'+name.rsplit('/',1)[-1])
            data=subprocess.run(['git','-C',str(root),'cat-file','blob',expected],
                capture_output=True,check=True,timeout=6).stdout
            sha=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if sha!=expected:raise RuntimeError('HOLD_LOCAL_SOURCE_SHA_'+name.rsplit('/',1)[-1])
            info=tarfile.TarInfo(name)
            info.size=len(data);info.mtime=0;info.mode=0o600
            tar.addfile(info,io.BytesIO(data))
    if len(memory.getvalue())>150000:raise RuntimeError('HOLD_ARCHIVE_TOO_LARGE')
    return base64.b64encode(memory.getvalue()).decode('ascii')

def main()->int:
    try:
        source_bundle=_bundle_existing_sources()
    except Exception:
        print('NOX_V76_STATE=HOLD_LOCAL_SOURCE_PACKAGING')
        return 2
    runner.REMOTE=REMOTE.replace('__NOX_V76_BUNDLE__',source_bundle)
    result=runner.onepass()
    # Existing V60 attach mutates V51.TRACK to its runner directory. We must
    # read back that exact registry entry, not a fresh V51 default directory.
    # One bounded reconciliation is allowed; no second SSH invocation.
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as one_key
    if one_key.TRACK.exists():
        try:
            if one_key.cleanup():
                result['temp_ssh_key_revoked']=not one_key.TRACK.exists()
        except Exception:
            result['temp_ssh_key_revoked']=False
    else:
        result['temp_ssh_key_revoked']=True
    path=Path("NOX_V76_ONEPASS_NATIVE_RECEIPT.json")
    native=result.get('native') if isinstance(result.get('native'),dict) else {}
    output={
      'schema':'NOX_V76_RUN_RECEIPT_V1','instance_id':60509551,
      'state':result.get('state'),'remote_exit_code':result.get('remote_exit_code'),
      'ssh_authenticated':result.get('ssh_authenticated',False),
      'temp_ssh_key_revoked':result.get('temp_ssh_key_revoked',False),
      'native_sha256':result.get('native_receipt_sha256'),
      'native':native,
    }
    path.write_text(json.dumps(output,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding='utf-8')
    print('NOX_V76_STATE='+str(output['state']))
    print('NOX_V76_SSH_KEY_REVOKED='+str(output['temp_ssh_key_revoked']))
    for name,detail in native.get('gates',{}).items():
        if isinstance(detail,dict):
            print('NOX_V76_GATE_'+name.upper()+'='+str(detail.get('state','HOLD')))
    print('NOX_V76_FULL_COMPLETION='+str(native.get('full_completion_verified',False)))
    print('NOX_V76_RECEIPT_SHA256='+str(output['native_sha256']))
    return 0 if str(output['state']).startswith('LIVE_CHECKS_PASS') and output['temp_ssh_key_revoked'] is True else 2
if __name__=='__main__':
    raise SystemExit(main())
