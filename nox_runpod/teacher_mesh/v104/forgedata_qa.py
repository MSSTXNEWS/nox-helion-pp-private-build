"""V104: provenance and privacy inventory of pre-existing FORGE datasets.
Never exports examples, outputs only counts. Never starts PEFT or full-weight jobs.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,os,re,hashlib,time
from collections import Counter
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V104_PRIVACY_LICENSE_CORPUS_ADMISSION_V1')
def emit(label,obj):
 s=json.dumps(obj,sort_keys=True,separators=(',',':'))
 if len(s)<1800:print('NATIVE_V104_'+label+'='+s)
base=Path('/root/nox/progress_pull_t784u')
wanted={'mix_understanding_t700u.jsonl','understanding_sft_t700u.jsonl',
 'understanding_pref_t700u.jsonl','pool_best.jsonl','dpo_pairs.jsonl',
 'anchors.jsonl','identity_sft_t733u.jsonl','s03_curriculum_t642u.jsonl'}
found={x:[] for x in wanted};models=[]
scan_dirs=0
for folder,dirs,files_in_dir in os.walk(base,followlinks=False):
 scan_dirs+=1
 depth=len(Path(folder).relative_to(base).parts)
 if scan_dirs>15000:break
 dirs[:]=[x for x in dirs if depth<9 and x not in ('node_modules','.git','logs','tmp','cache','venv','.venv','__pycache__') and not (Path(folder)/x).is_symlink()][:90]
 p=Path(folder)
 if p.name=='merged_hf' and 'config.json' in files_in_dir and not p.is_symlink():models.append(p)
 for name in wanted.intersection(files_in_dir):
  if not (p/name).is_symlink():found[name].append(p/name)
model=models[0] if len(models)==1 else Path('/root/nox/NO_MODEL_SELECTED')
hf={'exists':len(models)==1,'model_locator_count':len(models),'scanned_dirs':scan_dirs}
if model.is_dir():
 try:
  cfg=json.loads((model/'config.json').read_text(encoding='utf8')[:30000])
  hf.update({'model_type':str(cfg.get('model_type','UNKNOWN'))[:60],
    'architectures':(cfg.get('architectures') or [])[:3],
    'layers':cfg.get('num_hidden_layers'),
    'hidden_size':cfg.get('hidden_size'),
    'dtype':str(cfg.get('torch_dtype',cfg.get('dtype','UNKNOWN')))[:40],
    'vocab_size':cfg.get('vocab_size',None)})
  indexes=list(model.glob('*.safetensors.index.json'))
  if indexes:
   ind=json.loads(indexes[0].read_text(encoding='utf8')[:3_000_000])
   refs={str(x) for x in (ind.get('weight_map') or {}).values()}
   hf['referenced_shards']=len(refs)
   hf['all_references_exist']=bool(refs and all((model/x).is_file() for x in refs))
  hf['tokenizer_files_present']=any((model/x).exists() for x in ('tokenizer.json','tokenizer_config.json','vocab.json'))
 except Exception as e:hf['metadata_hold']=type(e).__name__
emit('MODEL',hf)
files=sorted(wanted)
SENSITIVE=re.compile(r'(?i)(?:\b(?:passport|medical|diagnosis|expediente|nie|email|phone)\b|\b(?:паспорт|диагноз|медицинск|адрес|полиц|врач|интервью)\w*|[A-Za-z0-9_.+\-]+@[A-Za-z0-9_.\-]+\.[a-z]{2,}|\b\+?[0-9][0-9\s().\-]{8,}\b)')
ALLOW={'apache-2.0','mit','cc0-1.0','cc-by-4.0','bsd-3-clause','public-domain'}
for rel in files:
 options=found.get(rel,[])
 p=options[0] if len(options)==1 else Path('/root/nox/NO_DATASET_SELECTED')
 result={'filename':rel,'present':len(options)==1,'locator_count':len(options),'private_text_exported':False}
 if len(options)!=1 or not p.is_file() or p.is_symlink():
  emit('DATASET',result);continue
 seen=set();dup=0;malformed=0;rows=0;pii=0;empty=0;licensed=0;consented=0;schema=Counter();lic=Counter();src=Counter()
 try:
  with p.open('rt',encoding='utf8',errors='replace') as f:
   for line in f:
    if rows>45000:break
    if len(line)>200000:
     malformed+=1;continue
    try:obj=json.loads(line)
    except ValueError:
     malformed+=1;continue
    if not isinstance(obj,dict):continue
    rows+=1
    schema.update(obj.keys())
    name=str(obj.get('license') or '').lower().strip()
    lic[name[:40] or 'MISSING']+=1
    if name in ALLOW:licensed+=1
    if obj.get('approved_for_training') is True and obj.get('owner_approved') is True:
     consented+=1
    if isinstance(obj.get('src'),str):src[obj['src'][:35]]+=1
    example=str(obj.get('prompt') or obj.get('user') or obj.get('text') or '')
    if not example.strip():empty+=1
    fingerprint=hashlib.sha256(' '.join(example.lower().split()).encode()).hexdigest()
    if fingerprint in seen:dup+=1
    seen.add(fingerprint)
    # Scan only in host RAM; do NOT export content or record-level hashes.
    if SENSITIVE.search(line):pii+=1
 except Exception as e:result['io_hold']=type(e).__name__
 result.update({'rows_scanned':rows,'malformed':malformed,'duplicate_prompts':dup,
  'sensitive_indicator_rows':pii,'empty_prompts':empty,
  'license_allowlist_rows':licensed,'explicit_owner_training_approved_rows':consented,
  'license_counts':lic.most_common(6),'top_schema_keys':schema.most_common(15),
  'source_count':len(src)})
 emit('DATASET',result)
print('NATIVE_V104_NO_DATASET_EXPORT=true')
print('NATIVE_V104_NO_WEIGHT_TRAINING_STARTED=true')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();okay=False;ssh.REMOTE=REMOTE
 old=ssh.api
 def gate(method,path,key,data=None):
  for i in range(4):
   try:
    r=old(method,path,key,data)
    if method=="POST" and path.endswith('/ssh/'):time.sleep(12)
    return r
   except RuntimeError as e:
    if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
    time.sleep((10,20,40)[i])
 ssh.api=gate
 try:
  with contextlib.redirect_stdout(out):okay=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V104_HOLD='+(v if v.startswith('HOLD_') and len(v)<90 else 'SSH'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:okay=False
  except Exception:okay=False
 lines=[]
 for line in out.getvalue().splitlines():
  if line.startswith(('NATIVE_V104_','TEMP_SSH_CLEANUP=')):
   print(line[:1900]);lines.append(line)
 passed=bool(okay and any(x.startswith('NATIVE_V104_MODEL=') and '"exists":true' in x for x in lines) and
             any(x.startswith('NATIVE_V104_DATASET=') and '"present":true' in x and '"rows_scanned":' in x for x in lines) and
             'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
 print('NOX_V104_CORPUS_PROVENANCE_AUDIT='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
