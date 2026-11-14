"""Inspect installed integration seams, not private runtime data or credentials."""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as bridge

REMOTE = r'''
set -euo pipefail
python3 - <<'PYREMOTE'
import ast, json, hashlib, re, configparser, shlex, os
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_ONEPASS_BINDING_SOURCE_V1')
def emit(k,v):
 s=json.dumps(v,ensure_ascii=True,separators=(',',':'))
 if len(s)<730:print('NATIVE_BIND_'+k+'='+s)
p=Path('/root/nox/scripts/chat_proxy.py')
if not p.is_file() or p.is_symlink() or p.stat().st_size>2000000:
 raise SystemExit('HOLD_CHAT_SOURCE')
raw=p.read_bytes();tree=ast.parse(raw)
emit('SOURCE',{'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
funcs=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
for n in funcs:
 if n.col_offset==0 or any(w in n.name.lower() for w in ('auth','session','owner','post')):
  emit('FUNCTION',{'name':n.name,'args':[a.arg for a in n.args.args],'line':n.lineno,'lines':n.end_lineno-n.lineno+1})
for n in tree.body:
 if isinstance(n,(ast.Import,ast.ImportFrom)):emit('IMPORT',ast.unparse(n))
# Redact literals in credential-bearing expressions and high-entropy strings.
class Safe(ast.NodeTransformer):
 def visit_Assign(self,n):
  names=' '.join(ast.unparse(t) for t in n.targets).lower()
  if any(w in names for w in ('password','passwd','secret','token','credential','api_key')) and isinstance(n.value,(ast.Constant,ast.Dict,ast.List)):
   n.value=ast.Constant('<REDACTED>');return n
  return self.generic_visit(n)
 def visit_Constant(self,n):
  if isinstance(n.value,str):
   s=n.value
   if len(s)>240 or re.search(r'(?i)(?:github_pat_|ghp_|sk-[A-Za-z0-9]|Bearer\s+[A-Za-z0-9]|[A-Za-z0-9+/=_-]{45,})',s):
    return ast.copy_location(ast.Constant('<LONG_OR_SENSITIVE_LITERAL>'),n)
  return n
selected=[]
for name in ('_build_messages','_proxy_completion'):
 selected += [n for n in funcs if n.name==name]
selected += [n for n in funcs if any(w in n.name.lower() for w in ('auth','session','owner')) and n.end_lineno-n.lineno<90][:8]
used=set();budget=420
for n in selected:
 if n.lineno in used:continue
 used.add(n.lineno)
 safe=Safe().visit(ast.parse(ast.unparse(n)))
 lines=ast.unparse(ast.fix_missing_locations(safe)).splitlines()
 emit('BLOCK',{'function':n.name,'source_lines':len(lines)})
 for i,line in enumerate(lines[:min(budget,160)],1):
  emit('LINE',{'fn':n.name,'n':i,'code':line[:550]})
  budget-=1
 if budget<=0:break
# Existing trainer config paths only; never export environment values or logs.
cfg=configparser.ConfigParser(interpolation=None,strict=False)
for f in Path('/etc/supervisor/conf.d').glob('*.conf'):
 try:cfg.read(f)
 except Exception:pass
for sec in cfg.sections():
 if not any(w in sec for w in ('volta','train-worm','teacher-serve')):continue
 cmd=cfg.get(sec,'command',fallback='')
 paths=re.findall(r'/[A-Za-z0-9_./-]+\.py',cmd)
 emit('TRAINER_PATH',{'service':sec,'scripts':paths[:3]})
 for path in paths[:1]:
  f=Path(path)
  if not f.is_file() or f.is_symlink() or f.stat().st_size>400000:continue
  data=f.read_bytes();t=ast.parse(data)
  emit('TRAINER_SOURCE',{'script':f.name,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)})
  for n in ast.walk(t):
   if isinstance(n,ast.Assign):
    names=' '.join(ast.unparse(x) for x in n.targets)
    if re.fullmatch(r'(?:BASE_MODEL|MODEL_DIR|MODEL_PATH|MODEL_ID|STUDENT_MODEL|DATA_PATH|DATASET_PATH|OUTPUT_DIR|MAX_LEN|MAX_LENGTH|SEQ_LEN|BATCH_SIZE|GRAD_ACCUM|DEVICE|DTYPE)',names):
     s=ast.unparse(Safe().visit(n))
     emit('TRAINER_SETTING',{'name':names,'code':s[:500]})
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
