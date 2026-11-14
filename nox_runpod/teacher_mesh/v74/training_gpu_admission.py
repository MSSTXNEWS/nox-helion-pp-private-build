"""NOX V74: true GPU1/base-weights/trainer and chat-aware admission.

Runs as one read-only native SSH probe in EXISTING NOX. Refuses false
training claims: no optimizer step, downloads, adapter, extra model or scheduler.
Only owned authorized OneHost can start a full-weight job after hard gates.
"""
from __future__ import annotations
import contextlib
import io
import json
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as bridge

_old_api=bridge.api
def _api_with_key_settle(method,path,key,data=None):
    # Vast rate limiting is transient; retry only idempotent GET requests.
    # Never repeat POST/DELETE automatically: an SSH-key mutation may have landed.
    for attempt in range(4):
        try:
            result=_old_api(method,path,key,data)
            if method=="POST" and path.endswith("/ssh/"):time.sleep(18)
            return result
        except RuntimeError as exc:
            if method!="GET" or str(exc)!="HOLD_VAST_API_HTTP_429" or attempt==3:
                raise
            time.sleep((10,20,40)[attempt])

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,json,stat,shutil,subprocess,configparser,shlex,hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V74_GPU1_DIRECT_WEIGHT_TRAINING_ADMISSION_V1')
root=Path('/root/nox')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
      '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
stop=any(Path(p).exists() for p in STOP)
try:
    gpu=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu',
                       '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=12)
    gpus=[]
    if gpu.returncode==0:
        for line in gpu.stdout.splitlines()[:2]:
            f=[x.strip() for x in line.split(',')]
            if len(f)==7 and f[0].isdigit() and all(v.isdigit() for v in f[2:]):
                gpus.append({'id':int(f[0]),'name':f[1][:35],
                   'total_mb':int(f[2]),'free_mb':int(f[3]),
                   'used_mb':int(f[4]),'gpu_util_pct':int(f[5]),'temp_c':int(f[6])})
except (OSError,subprocess.TimeoutExpired):gpus=[]
print('NATIVE_TRAIN_GPU='+json.dumps(gpus,separators=(',',':')))

# Existing service supervision and training scripts; no restart, no source edits.
services={}
try:
    for name in ('nox-train-worm-t811u','nox-teacher-serve-t811u',
                 'nox-agent-tuner-t858u','nox-downloads-t802u'):
        p=subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=7)
        parts=p.stdout.strip().split()
        services[name]=parts[1] if p.returncode==0 and len(parts)>1 else 'UNKNOWN'
except (OSError,subprocess.TimeoutExpired):pass
print('NATIVE_TRAIN_SERVICES='+json.dumps(services,separators=(',',':')))
trainer_script=Path('/root/nox/scripts/train_worm_t811u.py')
trainer_proof={'present':False}
try:
    if trainer_script.is_file() and not trainer_script.is_symlink():
        data=trainer_script.read_bytes()
        txt=data.decode('utf-8','replace')
        trainer_proof={'present':True,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
           'import_peft':('import peft' in txt or 'from peft' in txt),
           'explicit_lora_call':any(k in txt for k in ('get_peft_model(', 'LoraConfig(', 'PeftModel(')),
           'direct_base_weight_delta_receipt_found':False}
except OSError:pass
print('NATIVE_TRAIN_SOURCE='+json.dumps(trainer_proof,separators=(',',':')))

# Only detect already-local HF trainable models with known size, no model load.
models=[]
roots=(root/'models',root/'forge',root/'training')
configs=0
for base in roots:
    if not base.is_dir():continue
    for parent,dirs,files in os.walk(base,followlinks=False):
        depth=len(Path(parent).relative_to(base).parts)
        dirs[:]=[d for d in dirs if depth<4 and d not in ('.git','.cache','.ssh','venv','.venv','node_modules')][:90]
        if 'config.json' not in files:continue
        configs+=1
        folder=Path(parent)
        try:
            config=json.loads((folder/'config.json').read_text()[:30000])
            model_type=config.get('model_type','UNKNOWN')
            if not isinstance(model_type,str):model_type='UNKNOWN'
        except (OSError,ValueError):model_type='UNKNOWN'
        shards=[]
        for pat in ('*.safetensors','pytorch_model*.bin'):
            for path in folder.glob(pat):
                try:
                    z=path.lstat()
                    if stat.S_ISREG(z.st_mode) and 10_000_000<z.st_size<35_000_000_000:
                        shards.append(z.st_size)
                except OSError:pass
        if shards and len(models)<12:
            models.append({'model_type':model_type[:40],
              'shard_count':len(shards),'weights_bytes':sum(shards),
              'cpu_training_abi_verified':False,
              'independent_gpu1_load_verified':False,
              'source_path_hint':hashlib.sha256(str(folder).encode()).hexdigest()[:12]})
        if configs>120:break
    if configs>120:break
print('NATIVE_TRAIN_LOCAL_HF='+json.dumps({'models':models,'configs_scanned':configs},separators=(',',':')))

# Private contents of datasets never leave Vast. Read only readiness gates.
dataset_candidates=0
approved=0
for folder in (root/'datasets',root/'training',root/'forge',root/'distillation'):
    if not folder.is_dir():continue
    for base,dirs,files in os.walk(folder,followlinks=False):
        depth=len(Path(base).relative_to(folder).parts)
        dirs[:]=[d for d in dirs if depth<3 and d not in ('.git','venv','.venv','models','checkpoints','weights')][:50]
        for name in files:
            if not name.endswith('.jsonl'):continue
            p=Path(base)/name
            try:
                st=p.lstat()
                if not stat.S_ISREG(st.st_mode) or st.st_size>25_000_000:continue
                dataset_candidates+=1
                first=[]
                with p.open(encoding='utf-8',errors='replace') as f:
                    for line in f:
                        if line.strip():
                            row=json.loads(line)
                            first.append(row)
                        if len(first)>=4:break
                if len(first)>=4 and all(isinstance(v,dict) and
                    v.get('rights_verified') is True and v.get('privacy_approved') is True and
                    all(isinstance(v.get(k),str) and v.get(k) for k in ('prompt','completion','source_uri')) for v in first):
                    approved+=1
            except (OSError,ValueError,TypeError):continue
            if dataset_candidates>100:break
        if dataset_candidates>100:break
    if dataset_candidates>100:break
print('NATIVE_TRAIN_DATASETS='+json.dumps({'jsonl_candidates':dataset_candidates,
 'first_4_rows_rights_and_privacy_approved':approved,
 'train_holdout_source_disjointness_verified':False},separators=(',',':')))

# Actual job processes (only admitted script basenames; no command or data export).
activities={label:0 for label in ('train_worm_t811u.py','direct_weights_smoke.py',
                                  'torchrun','accelerate','llama-server')}
for name in os.listdir('/proc'):
    if not name.isdigit():continue
    try:
        if int(name)==os.getpid():continue
        argv=[v.decode('utf-8','replace') for v in
              (Path('/proc')/name/'cmdline').read_bytes()[:1800].split(b'\0') if v]
        if not argv or '-c' in argv[:2]:continue
        exe=Path(argv[0]).name
        for label in activities:
            if exe==label or any(Path(v).name==label for v in argv[1:6]):
                activities[label]+=1
    except (OSError,ValueError):pass
print('NATIVE_TRAIN_PROCESSES='+json.dumps(activities,separators=(',',':')))
free=shutil.disk_usage('/workspace').free
gpu1=next((g for g in gpus if g['id']==1),None)
# No download or optimizer outputs can be authorized solely by aggregate free bytes.
hold=[]
if stop:hold.append('GLOBAL_STOP')
if not gpu1:hold.append('GPU1_MISSING')
elif gpu1['free_mb']<12288:hold.append('GPU1_FULL_WEIGHT_HEADROOM')
if not models:hold.append('VETTED_TRAINABLE_HF_BASE_NOT_PINNED')
if approved<2:hold.append('AUDITED_TRAIN_AND_HOLDOUT_DATASET')
else:hold.append('TRAIN_HOLDOUT_DISJOINTNESS_UNVERIFIED')
hold.extend(('OWNER_RESTORE_NOT_PROVEN','NATIVE_ONEHOST_TRAINING_LEASE_NOT_PROVEN'))
print('NATIVE_TRAIN_ADMISSION='+json.dumps({
 'state':'HOLD_FULL_BASE_WEIGHT_TRAINING' if hold else 'READY_OWNER_GATE_ONLY',
 'hold_reasons':hold,'free_disk_bytes':free,
 'chat_main_gpu_reserved':0,'teacher_distillation_gpu':1,
 'full_parameter_optimizer_steps_executed_this_probe':0,
 'checkpoint_changed_by_probe':False,'active_GGUF_changed_by_probe':False,
 'distillation_completed_claim':False,
 'no_user_facing_second_model':True,
 'native_training_launched':False},separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main()->int:
    bridge.REMOTE=REMOTE
    bridge.api=_api_with_key_settle
    console=io.StringIO()
    completed=False
    cleanup=False
    try:
        with contextlib.redirect_stdout(console):
            completed=bridge.probe()
    except Exception as e:
        s=str(e)
        print("NOX_V74_HOLD="+s if s.startswith("HOLD_") and len(s)<90 else "NOX_V74_HOLD=NATIVE_TRAIN_PROBE")
    finally:
        try:
            with contextlib.redirect_stdout(console):
                cleanup=bridge.cleanup()
        except Exception:
            print("NOX_V74_HOLD=SSH_KEY_REVOCATION")
    required=['NATIVE_TRAIN_GPU=','NATIVE_TRAIN_SOURCE=','NATIVE_TRAIN_DATASETS=',
              'NATIVE_TRAIN_ADMISSION=']
    observed=[]
    for line in console.getvalue().splitlines():
        if line.startswith(('NATIVE_TRAIN_','TEMP_SSH_CLEANUP=')) and len(line)<790:
            print(line)
            observed.append(line.split('=',1)[0]+'=')
    good=bool(completed and cleanup and all(k in observed for k in required))
    print('NOX_V74_NATIVE_WEIGHT_ADMISSION_READBACK='+str(good).lower())
    print('NOX_V74_OPTIMIZER_STEPS_STARTED=0')
    return 0 if good else 2

if __name__=='__main__':raise SystemExit(main())
