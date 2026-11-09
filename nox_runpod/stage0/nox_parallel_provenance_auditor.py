#!/usr/bin/env python3
"""NOX controller CPU-only validation worker; never modifies teacher/source/model weights."""
import datetime,hashlib,json,os,pathlib,time,fcntl,sys
R=pathlib.Path('/workspace/nox');D=R/'distillation';S=R/'dispatcher/dual_gpu'
S.mkdir(parents=True,exist_ok=True)
node=sys.argv[1] if len(sys.argv)>1 else "unknown"
log=S/(node+'_auditor.json')
def atom(data):
 t=log.with_suffix('.tmp')
 with t.open('w',encoding='utf-8') as f:
  json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,log)
lock=(S/(node+'_auditor.lock')).open('a+')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:print('AUDITOR_ALREADY_RUNNING');sys.exit(0)
while not (S/('STOP_'+node)).exists():
 samples=0;files=0;bad=0;teachers={};unique=set()
 for f in D.glob('*.jsonl'):
  if f.name.startswith('NOX_A5000_CURATED_') or f.stat().st_size>300_000_000:continue
  files+=1
  try:
   with f.open(encoding='utf-8') as inp:
    for line in inp:
     try:
      row=json.loads(line)
      if not isinstance(row,dict):bad+=1;continue
      text=str(row.get('text') or '')
      if len(text)<80:bad+=1;continue
      ident=hashlib.sha256(text.encode('utf-8')).hexdigest()
      if ident in unique:continue
      unique.add(ident);samples+=1
      teacher=str(row.get('teacher') or f.name)[:120]
      teachers[teacher]=teachers.get(teacher,0)+1
     except (ValueError,TypeError):bad+=1
  except OSError:bad+=1
 out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'node':node,
      'status':'SOURCE_PROVENANCE_AUDIT_NOT_WEIGHT_TRAINING','files':files,'unique_samples':samples,
      'invalid_records':bad,'teachers':teachers,'full_weight_absorption_verified':False}
 atom(out);print(json.dumps(out,ensure_ascii=False),flush=True)
 for _ in range(60):
  if (S/('STOP_'+node)).exists():break
  time.sleep(1)
