#!/usr/bin/env python3
"""Run independent bounded storage/browser/media diagnostics on the same host."""
import base64,concurrent.futures,hashlib,json,os,re,stat,subprocess,tempfile
from pathlib import Path
try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox')
PINS={
 'owner_storage_reclaim.py':'1d6d89844a4402288dc812b7a1f38abb90521a7af00a1d83d29409cb5a9c0b9c',
 'owner_browser_diagnostic.py':'52561a3f8503ad1ebd35df92cb8dbff3c2a6381dbecb5d24c6e74be20257575f',
}
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)
def main():
 request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
 if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):raise RuntimeError('HOLD_OWNER_CONTEXT')
 paths=[]
 for name,pin in PINS.items():
  raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
  if hashlib.sha256(raw).hexdigest()!=pin:raise RuntimeError('HOLD_AUX_SOURCE_PIN')
  compile(raw,name,'exec');path=ROOT/'scripts'/name
  if any(p.is_symlink() for p in (*path.parents,path)):raise RuntimeError('HOLD_AUX_SYMLINK')
  if path.exists():
   meta=path.stat()
   if not stat.S_ISREG(meta.st_mode) or meta.st_size>1024*1024 or hashlib.sha256(path.read_bytes()).hexdigest()!=pin:raise RuntimeError('HOLD_AUX_INSTALLED_CHANGED')
  else:
   fd,tmp=tempfile.mkstemp(prefix='.owner-audit-',dir=path.parent)
   try:
    os.fchmod(fd,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
   finally:
    if os.path.exists(tmp):os.unlink(tmp)
  paths.append(path)
 env={**os.environ,'NOX_STORAGE_ACTION':'AUDIT','CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}
 def execute(path):
  proc=subprocess.run(['/usr/bin/python3',str(path)],env=env,capture_output=True,text=True,timeout=115)
  lines=[]
  for line in proc.stdout.splitlines():
   if line.startswith('NOX_MAINT_REPAIR=') and len(line)<160000:
    json.loads(line[len('NOX_MAINT_REPAIR='):]);lines.append(line)
  return path.name,proc.returncode,lines
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(execute,paths))
 for name,code,lines in results:
  for line in lines:print(line,flush=True)
  emit('aux_diagnostic_exit',{'name':name,'exit_code':code})
 if any(code for _,code,_ in results):raise RuntimeError('HOLD_AUX_DIAGNOSTIC_FAILED')
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:
  code=str(exc);emit('aux_diagnostic_hold',{'reason':code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else type(exc).__name__});raise SystemExit(2)
