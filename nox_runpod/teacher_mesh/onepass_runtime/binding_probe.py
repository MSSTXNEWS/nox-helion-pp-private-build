"""Inspect existing native memory methods; no user records or credentials."""
from __future__ import annotations
import contextlib, io, time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as bridge
REMOTE=r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,json,hashlib,re,configparser,shlex
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
def emit(k,v):
 s=json.dumps(v,ensure_ascii=False,separators=(',',':'))
 if len(s)<730:print('NATIVE_BIND_'+k+'='+s)
p=Path('/root/nox/scripts/chat_proxy.py');raw=p.read_bytes();tree=ast.parse(raw)
emit('SOURCE',{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
class Safe(ast.NodeTransformer):
 def visit_Constant(self,n):
  if isinstance(n.value,str) and (len(n.value)>350 or re.search(r'(?:github_pat_|ghp_|sk-[A-Za-z0-9]|Bearer\s+[A-Za-z0-9]|[A-Za-z0-9+/=_-]{45,})',n.value)):
   return ast.copy_location(ast.Constant('<REDACTED_LONG_LITERAL>'),n)
  return n
names=('_s03_augment','_s03_persist_pair','_infinite_persist','s03_recall_api','s03_remember_api','s03_status','chat_api','chat','_augment','_is_public_path')
for n in tree.body:
 if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names:
  code=ast.unparse(ast.fix_missing_locations(Safe().visit(ast.parse(ast.unparse(n)))))
  for i,line in enumerate(code.splitlines(),1):emit('LINE',{'fn':n.name,'n':i,'code':line[:620]})
# Imports and memory constructors in the first 140 source lines only.
for n in ast.walk(tree):
 if getattr(n,'lineno',100000)>140:continue
 if isinstance(n,(ast.Import,ast.ImportFrom)):
  emit('MEM_IMPORT',ast.unparse(n))
 if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and any(w in x.id.lower() for w in ('s03','infinite','memory')) for x in n.targets):
  emit('MEM_INIT',ast.unparse(Safe().visit(n))[:600])
# Resolve supervisor-launched shell wrappers to actual training script paths.
cfg=configparser.ConfigParser(interpolation=None,strict=False)
for f in Path('/etc/supervisor/conf.d').glob('*.conf'):
 try:cfg.read(f)
 except Exception:pass
for sec in cfg.sections():
 if 'train-volta' not in sec:continue
 command=cfg.get(sec,'command',fallback='')
 paths=re.findall(r'/[A-Za-z0-9_./-]+\.(?:sh|py)',command)
 emit('VOLTA_WRAPPER',{'paths':paths[:3]})
 for path in paths[:2]:
  f=Path(path)
  if not f.is_file() or f.is_symlink() or f.stat().st_size>100000:continue
  text=f.read_text(errors='replace')
  if f.suffix=='.sh':
   emit('VOLTA_PY_PATHS',re.findall(r'/[A-Za-z0-9_./-]+\.py',text)[:6])
   for line in text.splitlines():
    if re.match(r'^(?:export )?(?:CUDA_VISIBLE_DEVICES|PYTORCH_CUDA_ALLOC_CONF|NOX_(?:MODEL|BASE|BATCH|SEQ|GRAD|TRAIN|DEVICE)[A-Z_]*|OMP_NUM_THREADS)=',line):emit('VOLTA_SAFE_CONFIG',line[:500])
print('NATIVE_BIND_PRIVATE_RECORDS_EXPORTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
 original=bridge.api
 def settled(method,path,key,data=None):
  for attempt in range(4):
   try:
    out=original(method,path,key,data)
    if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
    return out
   except RuntimeError as exc:
    if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or attempt==3:raise
    time.sleep((10,20,40)[attempt])
 bridge.api=settled;bridge.REMOTE=REMOTE
 output=io.StringIO();ok=False
 try:
  with contextlib.redirect_stdout(output):ok=bridge.probe()
 finally:
  with contextlib.redirect_stdout(output):
   if not bridge.cleanup():ok=False
 for line in output.getvalue().splitlines():
  if line.startswith(('NATIVE_BIND_','TEMP_SSH_CLEANUP=')):print(line)
 return 0 if ok and 'NATIVE_BIND_SOURCE=' in output.getvalue() else 2
if __name__=='__main__':raise SystemExit(main())
