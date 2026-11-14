"""V105: ONEPASS approved local owner-template SFT+holdout curation.
Small private corpus only; no adapters, model changes, source deletion, API or
parallel scheduler. All personal/suspected-sensitive examples are excluded.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,json,hashlib,re,shutil,uuid,stat,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V105_OWNER_TEMPLATE_CURATED_SFT_V1')
def emit(x):print('NATIVE_V105_RESULT='+json.dumps(x,sort_keys=True,separators=(',',':')))
STOPS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def stopped():return any(Path(x).exists() for x in STOPS)
root=Path('/root/nox/progress_pull_t784u')
target=Path('/root/nox/forge/curated_owner_sft_v105')
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return h.hexdigest()
SENSITIVE=re.compile(r'(?i)(?:[a-z0-9._+\-]+@[a-z0-9._\-]+\.[a-z]{2,}|\b(?:passport|medical|diagnosis|expediente|patient|bank|social.security|password|secret|token)\b|\b(?:паспорт|диагноз|медицинск|адрес|полиц|врач|интервью|здоровь|банковск)\w*|\b\+?[0-9][0-9\s().\-]{8,}\b)')
def valid(obj):
 if not isinstance(obj,dict):return 'invalid',None,None
 if str(obj.get('license') or '').strip().lower()!='internal-owner-templates':return 'rights_hold',None,None
 if not isinstance(obj.get('provenance'),str) or not obj['provenance'].strip():return 'provenance_hold',None,None
 if obj.get('is_negative') is True:return 'negative',None,None
 prompt=obj.get('prompt');answer=obj.get('answer')
 if not isinstance(prompt,str) or not isinstance(answer,str):return 'missing_pair',None,None
 if not 8<=len(prompt.strip())<=3500 or not 1<=len(answer.strip())<=5000:return 'length',None,None
 if SENSITIVE.search(prompt) or SENSITIVE.search(answer):return 'private_hold',None,None
 return 'eligible',prompt.strip(),answer.strip()
def split_key(prompt):
 normalized=' '.join(prompt.casefold().split())
 digest_key=hashlib.sha256(normalized.encode('utf8')).digest()
 return (digest_key[0]%10)==0
def verified_dir(dest):
 try:
  if dest.is_symlink() or not dest.is_dir():return False
  m=json.loads((dest/'manifest.json').read_text(encoding='utf8'))
  if m.get('schema')!='NOX_FORGE_OWNER_SFT_V105':return False
  for name in ('train.jsonl','holdout.jsonl'):
   p=dest/name
   if not p.is_file() or p.is_symlink() or digest(p)!=m.get(name+'_sha256'):return False
  return True
 except Exception:return False
try:
 if stopped():raise RuntimeError('HOLD_STOP')
 if shutil.disk_usage('/root/nox').free<10*1024**3:raise RuntimeError('HOLD_DISK_RESERVE')
 candidates=[]
 for directory,dirs,files in os.walk(root,followlinks=False):
  depth=len(Path(directory).relative_to(root).parts)
  dirs[:]=[d for d in dirs if depth<8 and d not in ('venv','.venv','.git','node_modules') and not (Path(directory)/d).is_symlink()][:90]
  if 'understanding_sft_t700u.jsonl' in files:
   p=Path(directory)/'understanding_sft_t700u.jsonl'
   if p.is_file() and not p.is_symlink():candidates.append(p)
 if len(candidates)!=1:raise RuntimeError('HOLD_UNIQUE_SOURCE_COUNT_'+str(len(candidates)))
 source=candidates[0];source_hash=digest(source)
 if target.exists():
  if not verified_dir(target):raise RuntimeError('HOLD_EXISTING_CORPUS_MISMATCH')
  manifest=json.loads((target/'manifest.json').read_text(encoding='utf8'))
  if manifest.get('source_sha256')!=source_hash:raise RuntimeError('HOLD_SOURCE_DRIFT')
  emit({'state':'EXISTING_CURATED_CORPUS_VERIFIED','train_rows':manifest.get('train_rows'),
   'holdout_rows':manifest.get('holdout_rows'),'data_deleted':False,'weights_changed':False,
   'train_sha256':manifest.get('train.jsonl_sha256'),'holdout_sha256':manifest.get('holdout.jsonl_sha256')})
 else:
  counts={};seen=set();tr=[];hold=[]
  with source.open('rt',encoding='utf8',errors='replace') as f:
   for line in f:
    if len(line)>220000:raise RuntimeError('HOLD_LONG_LINE')
    try:obj=json.loads(line)
    except ValueError:raise RuntimeError('HOLD_MALFORMED_SOURCE')
    state,prompt,answer=valid(obj)
    counts[state]=counts.get(state,0)+1
    if state!='eligible':continue
    key=hashlib.sha256(' '.join(prompt.casefold().split()).encode('utf8')).hexdigest()
    if key in seen:
     counts['duplicate']=counts.get('duplicate',0)+1
     continue
    seen.add(key)
    rec={'messages':[{'role':'user','content':prompt},{'role':'assistant','content':answer}],
      'source_license':'internal-owner-templates','source_provenance':obj['provenance'],
      'source_row_sha256':hashlib.sha256(line.encode('utf8')).hexdigest()}
    if split_key(prompt):hold.append(rec)
    else:tr.append(rec)
  if len(tr)<300 or len(hold)<30:raise RuntimeError('HOLD_INSUFFICIENT_SAFE_EXAMPLES')
  if stopped():raise RuntimeError('HOLD_STOP')
  parent=target.parent
  if parent.is_symlink():raise RuntimeError('HOLD_PARENT_SYMLINK')
  parent.mkdir(mode=0o700,parents=True,exist_ok=True)
  stage=parent/('.curated_v105_stage_'+str(os.getpid()))
  if stage.exists():raise RuntimeError('HOLD_STAGE_CONFLICT')
  stage.mkdir(mode=0o700)
  try:
   manifest={'schema':'NOX_FORGE_OWNER_SFT_V105','source_sha256':source_hash,
    'source_name':source.name,'train_rows':len(tr),'holdout_rows':len(hold),
    'filter_counts':counts,'contains_raw_owner_legal_or_medical_records':False,
    'license':'internal-owner-templates','dataset_private_only':True,
    'full_weight_training_started':False,'optimizer_steps_verified':0,
    'manual_rights_review_for_external_distribution_required':True}
   for name,rows in (('train.jsonl',tr),('holdout.jsonl',hold)):
    out=stage/name
    with out.open('x',encoding='utf8') as o:
     os.chmod(out,0o600)
     for rec in rows:o.write(json.dumps(rec,ensure_ascii=False,sort_keys=True)+'\n')
     o.flush();os.fsync(o.fileno())
    manifest[name+'_sha256']=digest(out)
   m=stage/'manifest.json'
   with m.open('x',encoding='utf8') as o:
    os.chmod(m,0o600)
    json.dump(manifest,o,sort_keys=True,ensure_ascii=False,indent=2)
    o.flush();os.fsync(o.fileno())
   if stopped():raise RuntimeError('HOLD_STOP')
   os.rename(stage,target)
  finally:
   if stage.exists():raise RuntimeError('HOLD_STAGE_INCOMPLETE_REVIEW_REQUIRED')
  if not verified_dir(target):raise RuntimeError('HOLD_MANIFEST_READBACK')
  emit({'state':'CURATED_PRIVATE_SFT_AND_HOLDOUT_VERIFIED',
   'train_rows':len(tr),'holdout_rows':len(hold),'filtered_counts':counts,
   'train_sha256':manifest['train.jsonl_sha256'],
   'holdout_sha256':manifest['holdout.jsonl_sha256'],
   'source_sha256':source_hash,'weights_changed':False,
   'training_started':False,'data_deleted':False})
except Exception as e:
 x=str(e)
 emit({'state':x if x.startswith('HOLD_') and len(x)<100 else 'HOLD_CORPUS_CURATION',
  'error_type':type(e).__name__,'weights_changed':False,'data_deleted':False})
print('NATIVE_V105_USER_RECORDS_EXPORTED=false')
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
  x=str(e);print('NOX_V105_HOLD='+(x if x.startswith('HOLD_') and len(x)<90 else 'SSH'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:okay=False
  except Exception:okay=False
 lines=[]
 for line in out.getvalue().splitlines():
  if line.startswith(('NATIVE_V105_RESULT=','TEMP_SSH_CLEANUP=')):
   print(line[:1850]);lines.append(line)
 passed=bool(okay and any(('CURATED_PRIVATE_SFT_AND_HOLDOUT_VERIFIED' in x or 'EXISTING_CURATED_CORPUS_VERIFIED' in x) for x in lines))
 print('NOX_V105_PRIVATE_CORPUS_ACCEPTED='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
