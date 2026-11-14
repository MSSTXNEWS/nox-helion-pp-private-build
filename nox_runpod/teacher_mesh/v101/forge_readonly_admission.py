"""V101: physical full-weight FORGE admission for two V100s, read-only.
Do not download, stop services, read personal datasets, import models, or train.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,json,subprocess,shutil,hashlib,stat,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V101_FULL_WEIGHT_TRAINABLE_STUDENT_ADMISSION_V1')
def emit(n,obj):
 s=json.dumps(obj,separators=(',',':'),sort_keys=True)
 if len(s)<4500:print('NATIVE_V101_'+n+'='+s)
STOP=any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP'))
try:
 out=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8)
 gpu=[]
 if out.returncode==0:
  for line in out.stdout.splitlines()[:4]:
   values=[v.strip() for v in line.split(',')]
   if len(values)==7 and values[0].isdigit() and all(v.isdigit() for v in values[2:]):
    gpu.append(dict(index=int(values[0]),name=values[1],vram_total_mib=int(values[2]),vram_free_mib=int(values[3]),used_mib=int(values[4]),util_pct=int(values[5]),temperature_c=int(values[6])))
except Exception:gpu=[]
emit('GPU',gpu)
disk=shutil.disk_usage('/root/nox')
mem={}
try:
 for line in Path('/proc/meminfo').read_text().splitlines():
  if line.startswith(('MemTotal:','MemAvailable:','SwapTotal:','SwapFree:')):
   a=line.split()
   mem[a[0].rstrip(':')+'_mib']=int(a[1])//1024
except Exception:pass
emit('RESOURCES',{'stop_active':STOP,'disk_free_gib':round(disk.free/1024**3,2),'disk_total_gib':round(disk.total/1024**3,2),**mem})
services={}
for name in ('nox-proxy','nox-teacher-serve-t811u','nox-train-worm-t811u','nox-train-volta-t866u','nox-agent-tuner-t858u'):
 try:
  p=subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=6)
  words=p.stdout.split()
  services[name]=words[1] if words and p.returncode==0 else 'UNKNOWN'
 except Exception:services[name]='UNKNOWN'
emit('SUPERVISOR',services)
models=[]; jsonls=[];checked=0;visited=0;started=time.monotonic();seen=set()
roots=[Path('/root/nox/progress_pull_t784u'),Path('/root/nox/models'),Path('/root/nox/forge'),Path('/root/nox/training'),
 Path('/root/nox/checkpoints'),Path('/workspace/models'),Path('/workspace'),
 Path('/root/.cache/huggingface/hub')]
SKIP={'.git','node_modules','__pycache__','venv','.venv','dist','build','logs','tmp','temp','web','www','assets','images','images-staging','static','screenshots','films'}
for base in roots:
 if not base.is_dir() or base.is_symlink():continue
 for directory,dirs,files in os.walk(base,followlinks=False):
  if time.monotonic()-started>20 or visited>25000:break
  visited+=1
  depth=len(Path(directory).relative_to(base).parts)
  dirs[:]=[x for x in dirs if depth<7 and x not in SKIP and not (Path(directory)/x).is_symlink()][:100]
  p=Path(directory)
  if directory in seen:continue
  seen.add(directory)
  if 'config.json' in files and checked<600:
   checked+=1
   try:
    cfgfile=p/'config.json'
    if cfgfile.is_symlink() or cfgfile.stat().st_size>100000:continue
    cfg=json.loads(cfgfile.read_text(encoding='utf8'))
    architecture=(cfg.get('architectures') or [])
    dtype=cfg.get('torch_dtype',cfg.get('dtype','UNKNOWN'))
    shards=[];shardnames=set()
    for file in files:
     if (file.endswith('.safetensors') or file.startswith('pytorch_model') and file.endswith('.bin')):
      path=p/file
      st=path.stat()
      if stat.S_ISREG(st.st_mode):
       shards.append(st.st_size);shardnames.add(file)
    if len(models)<25 and sum(shards)>10000000:
     models.append({'folder_name':p.name[:70],'model_type':str(cfg.get('model_type','UNKNOWN'))[:50],
       'architecture':str(architecture[0] if architecture else 'UNKNOWN')[:65],
       'dtype':str(dtype)[:30],'shards':len(shards),
       'weights_bytes':sum(shards),'hidden_size':cfg.get('hidden_size',None),
       'layers':cfg.get('num_hidden_layers',None)})
   except Exception:pass
  if (str(base).startswith('/root/nox') or str(base)=='/workspace') and len(jsonls)<35:
   for file in files:
    if file.endswith('.jsonl') and (file.lower().startswith(('train','distill','knowledge','lesson','corpus','approved')) or 'dataset' in directory.lower()):
     try:
      path=p/file
      st=path.stat()
      if stat.S_ISREG(st.st_mode):
       jsonls.append({'parent':p.name[:50],'name':file[:60],'bytes':st.st_size})
     except OSError:pass
emit('HF_STUDENTS',{'checked_configs':checked,'dirs_visited':visited,'candidates':models})
emit('DATASETS',{'jsonl_count':len(jsonls),'candidate_files':jsonls[:20]})
# Verify existing V105 curated owner templates by SHA without exporting their text.
curated=Path('/root/nox/forge/curated_owner_sft_v105')
proven={}
for fname,expected,expected_lines in [
 ('train.jsonl','3530f0eddafb91bf913bd4c215116da30d53d53bcf3486f4b1ce3c42f4c5ca58',1927),
 ('holdout.jsonl','322a6d73630fc34b3532f00dd627b917197b9319ad5a560bc977871bcb31c5ee',227)]:
 p=curated/fname
 entry={'present':False,'sha_verified':False,'rows_verified':False}
 try:
  if p.is_file() and not p.is_symlink() and p.stat().st_size<50_000_000:
   h=hashlib.sha256();rows=0
   with p.open('rb') as f:
    for line in f:
     h.update(line);rows+=1
   entry={'present':True,'sha_verified':h.hexdigest()==expected,
          'rows_verified':rows==expected_lines,'rows':rows,'size_bytes':p.stat().st_size}
 except Exception:pass
 proven[fname]=entry
approved_corpus_proven=all(x['present'] and x['sha_verified'] and x['rows_verified'] for x in proven.values())
emit('CURATED_OWNER_DATA',{'files':proven,'train_holdout_verified':approved_corpus_proven,
                          'text_exported':False})

trainer={}
for file in ['/root/nox/scripts/train_qlora_35b_t866u.py','/root/nox/scripts/train_worm_t811u.py']:
 p=Path(file)
 if not p.is_file() or p.is_symlink():continue
 raw=p.read_bytes()
 trainer[p.name]={'sha256':hashlib.sha256(raw).hexdigest(),'peft_or_lora':any(x in raw for x in (b'LoraConfig',b'get_peft_model(',b'from peft',b'import peft')),'optimizer_step_source':b'optimizer.step(' in raw,'bytes':len(raw)}
emit('TRAINERS',trainer)
# External ciphertext without owner-key restore is not full training restore evidence.
full_weight_ready=bool(not STOP and disk.free>20*1024**3 and
 any(v.get('weights_bytes',0)>4_000_000_000 for v in models) and
 approved_corpus_proven and
 not trainer.get('train_qlora_35b_t866u.py',{}).get('peft_or_lora',False) and
 len(gpu)>=2 and gpu[1]['vram_free_mib']>=12288)
emit('ADMISSION',{'state':'SOURCE_INVENTORY_ONLY_NOT_TRAINING' if full_weight_ready else 'HOLD_FULL_WEIGHT_TRAINING',
'resource_gate':bool(len(gpu)>=2 and gpu[1]['vram_free_mib']>=12288 and disk.free>20*1024**3),
'trainable_base_candidate':any(v.get('weights_bytes',0)>4_000_000_000 for v in models),
'approved_dataset_proven':approved_corpus_proven,'owner_key_restore_proven':False,
'full_weight_optimizer_steps_verified':0,'training_started':False,'full_weight_trainer_without_adapters_verified':False,'full_checkpoint_disk_space_verified':disk.free>85*1024**3})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();good=False;ssh.REMOTE=REMOTE
 old=ssh.api
 def gate(method,path,key,data=None):
  for i in range(4):
   try:
    res=old(method,path,key,data)
    if method=="POST" and path.endswith('/ssh/'):time.sleep(12)
    return res
   except RuntimeError as e:
    if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
    time.sleep((10,20,40)[i])
 ssh.api=gate
 try:
  with contextlib.redirect_stdout(out):good=ssh.probe()
 except Exception as e:
  val=str(e);print('NOX_V101_HOLD='+(val if val.startswith('HOLD_') and len(val)<95 else 'SSH_NATIVE'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:good=False
  except Exception:good=False
 lines=[]
 for x in out.getvalue().splitlines():
  if x.startswith(('NATIVE_V101_','TEMP_SSH_CLEANUP=')):
   print(x[:4400]);lines.append(x)
 passed=bool(good and any(x.startswith('NATIVE_V101_ADMISSION=') for x in lines) and 'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
 print('NOX_V101_GPU_DATA_INVENTORY_VERIFIED='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
