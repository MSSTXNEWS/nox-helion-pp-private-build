#!/usr/bin/env python3
"""Install reviewed PC helpers and diagnose current chat/media without changing weights."""
from __future__ import annotations
import ast,base64,fcntl,hashlib,json,os,re,sqlite3,stat,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ROOT=Path('/root/nox');SCRIPTS=ROOT/'scripts'
PINS={
 'nox_cold_drive.py':('5093641452fb6500b407ce8d755768fb9e0e2d28a0b942731ad05485373ddbdb','4cdb6789d183e14eb3088c0d6174e0f28fc44c689f3c13fac856dfb54a13f5c2'),
 'nox_pc_export.py':(None,'957b8dce05e7c0c9439bb52f9f8af98a46ce939b8d441f306438b273f601118d'),
}
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},ensure_ascii=False,separators=(',',':')),flush=True)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path,limit=1000000):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  meta=os.fstat(f.fileno())
  if not stat.S_ISREG(meta.st_mode) or meta.st_size>limit:raise RuntimeError('HOLD_BOUNDED_REGULAR_FILE')
  raw=f.read(limit+1)
  if len(raw)>limit:raise RuntimeError('HOLD_BOUNDED_REGULAR_FILE')
  return raw
def atomic(path,raw):
 if path.is_symlink() or path.parent.is_symlink():raise RuntimeError('HOLD_PATH_LINK')
 fd,tmp=tempfile.mkstemp(prefix='.nox-owner-',dir=path.parent)
 try:
  os.fchmod(fd,0o600)
  with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def safe_code(exc):
 value=str(exc)
 return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def public_answer(text,expected,prompt=''):
 value=text.strip().strip('`*_ .!\r\n\t')
 return {'answer_numeric':value if re.fullmatch('-?[0-9]{1,6}',value or '') else None,
  'exact_pass':value==str(expected),'contains_expected_number':bool(re.search(r'(?<!\d)'+str(expected)+r'(?!\d)',text)),
  'has_honorific':bool(re.search(r'мессир|мой лорд',text,re.I)),
  'echoes_prompt':bool(prompt and prompt in text),'chars':len(text),'sha256':sha(text.encode()),'raw_text_exported':False}
def pc_helpers(request):
 changes=[]
 for name,(old,new) in PINS.items():
  path=SCRIPTS/name;raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
  if sha(raw)!=new:raise RuntimeError('HOLD_PC_HELPER_BUNDLE_PIN')
  compile(raw,name,'exec')
  previous=read(path) if path.exists() or path.is_symlink() else None
  current=sha(previous) if previous is not None else None
  if current not in (old,new):raise RuntimeError('HOLD_PC_HELPER_NATIVE_CHANGED')
  changes.append((path,previous,raw,current,new))
 backup=ROOT/'backup/owner_pc_helpers'/request
 backup.mkdir(parents=True,mode=0o700,exist_ok=False)
 installed=[]
 try:
  for path,previous,raw,current,new in changes:
   if previous is not None:atomic(backup/path.name,previous)
   if current!=new:atomic(path,raw);installed.append((path,previous))
   proc=subprocess.run([sys.executable,str(path),'--help'],capture_output=True,timeout=15)
   if proc.returncode or sha(read(path))!=new:raise RuntimeError('HOLD_PC_HELPER_VERIFY')
 except Exception:
  for path,previous in reversed(installed):
   if previous is not None:atomic(path,previous)
   else:path.unlink()
  raise
 result={'state':'INSTALLED_PC_CONNECTION_PENDING','files':[{'name':p.name,'sha256':n} for p,_,_,_,n in changes],
         'server_sources_deleted':False,'backups_transferred':False}
 connection=ROOT/'state/pc_shell/connection.json'
 if connection.is_file() and not connection.is_symlink():
  proc=subprocess.run([sys.executable,str(SCRIPTS/'nox_cold_drive.py'),'configure-pc'],capture_output=True,timeout=25)
  result['state']='PC_STORAGE_CONFIGURED' if proc.returncode==0 else 'INSTALLED_PC_CONFIGURATION_PENDING'
 return result
def source_excerpt(path,names):
 raw=read(path,250000);source=raw.decode();tree=ast.parse(source);parts=[]
 for node in tree.body:
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:
   text=ast.get_source_segment(source,node) or ''
   text=re.sub(r'(?im)^([^\n]*(?:password|secret|api_key|authorization|token)\w*\s*=\s*)[\"\'][^\"\'\n]+[\"\']',r'\1"[REDACTED]"',text)
   text=re.sub(r'(?:hf_|ghp_|github_pat_|sk-proj-)[A-Za-z0-9_-]{12,}','[REDACTED]',text)
   parts.append({'name':node.name,'source':text[:14000],'truncated':len(text)>14000})
 return {'path':str(path),'sha256':sha(raw),'functions':parts}
def launch_source():
 path=SCRIPTS/'start_chat_8081.sh';raw=read(path,60000);source=raw.decode()
 if re.search(r'(?i)(password|api_key|authorization|private.key|token)\s*=',source):
  return {'path':str(path),'sha256':sha(raw),'source_withheld':True}
 return {'path':str(path),'sha256':sha(raw),'source':source}
def saved_qa():
 path=ROOT/'kb/knowledge.sqlite'
 if path.is_symlink():raise RuntimeError('HOLD_S03_LINK')
 con=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2)
 try:
  con.execute('PRAGMA query_only=ON');deadline=time.monotonic()+3
  con.set_progress_handler(lambda:1 if time.monotonic()>deadline else 0,1000)
  rows=con.execute("SELECT row_id,dialog_id,substr(content,1,10000) FROM nox_v29_dialog_messages WHERE role='user' AND content LIKE '[QA nox_latency_%' ORDER BY row_id DESC LIMIT 3").fetchall()
  out=[]
  for row,did,prompt in rows:
   if not re.fullmatch(r'\[QA nox_latency_[a-f0-9]{10}\] Сколько будет 17 умножить на 19\? Ответь только числом\.',prompt):continue
   following=con.execute('SELECT role,substr(content,1,10000) FROM nox_v29_dialog_messages WHERE dialog_id=? AND row_id>? ORDER BY row_id LIMIT 3',(did,row)).fetchall()
   if following and following[0][0]=='assistant':out.append({'scope':'synthetic_arithmetic',**public_answer(following[0][1],323,prompt)})
   if len(following)==3 and following[1]==('user','Какое число ты только что получил? Ответь только этим числом.') and following[2][0]=='assistant':
    out.append({'scope':'synthetic_history',**public_answer(following[2][1],323,following[1][1])})
  return out
 finally:con.close()
def local_json(path):
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open('http://127.0.0.1:8081'+path,timeout=5) as response:return json.loads(response.read(150000))
def model_case(name,messages,expected):
 slots=local_json('/slots')
 if any(row.get('is_processing',row.get('processing',False)) for row in slots):return {'case':name,'state':'CHAT_BUSY_SKIPPED'}
 payload={'model':'NOX','messages':messages,'stream':True,'temperature':0,'seed':7,'max_tokens':64,
          'cache_prompt':True,'chat_template_kwargs':{'enable_thinking':False}}
 req=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));started=time.monotonic();first=None;answer='';done=False;reasoning_chars=0
 with opener.open(req,timeout=40) as response:
  for i,line in enumerate(response):
   if time.monotonic()-started>45 or i>2000 or len(line)>150000:raise RuntimeError('HOLD_CHAT_DIAG_LIMIT')
   if not line.startswith(b'data: '):continue
   data=line[6:].strip()
   if data==b'[DONE]':done=True;break
   frame=json.loads(data);delta=((frame.get('choices') or [{}])[0].get('delta') or {})
   token=delta.get('content') or ''
   reasoning_chars+=len(delta.get('reasoning_content') or '')
   if token:
    answer+=token
    if first is None and re.search(r'[^\s.…]',token):first=round((time.monotonic()-started)*1000)
 return {'case':name,'complete':done,'first_ms':first,'total_ms':round((time.monotonic()-started)*1000),
         'reasoning_chars':reasoning_chars,**public_answer(answer,expected,messages[-1]['content'])}
def media_diagnostic():
 state=ROOT/'state/owner_media';rows=[]
 for path in sorted(state.glob('prepare_result_*.json'))[-4:]:
  data=json.loads(read(path,20000));rows.append({key:data[key] for key in ('request','state','error','started','finished') if key in data})
 result={'results':rows}
 python=ROOT/'media/venv/bin/python'
 if not python.is_file():return dict(result,venv_present=False)
 marker=ROOT/'media/venv/nox-environment.json';doc=json.loads(read(marker,20000))
 pins=doc.get('pypi_pins') or []
 if not pins or len(pins)>40 or any(not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+',p) for p in pins):raise RuntimeError('HOLD_MEDIA_PACKAGE_SCOPE')
 env={**os.environ,'PIP_DISABLE_PIP_VERSION_CHECK':'1','PIP_NO_CACHE_DIR':'1','PIP_REQUIRE_VIRTUALENV':'1','CUDA_VISIBLE_DEVICES':''}
 argv=[str(python),'-m','pip','install','--dry-run','--no-deps','--ignore-installed','--only-binary=:all:','--index-url','https://pypi.org/simple',*pins]
 proc=subprocess.run(argv,capture_output=True,text=True,env=env,timeout=120)
 errors=[]
 for line in (proc.stdout+'\n'+proc.stderr).splitlines():
  match=re.search(r'(?:No matching distribution found for |Could not find a version that satisfies the requirement )([A-Za-z0-9_.+=<>-]+)',line)
  if match:errors.append({'package':match[1],'code':'NO_MATCHING_DISTRIBUTION'})
 result.update(pip_dry_run_returncode=proc.returncode,package_errors=errors,raw_output_exported=False)
 probe="import json,sys;print(json.dumps({'python':sys.version.split()[0]}));import torch,torchvision,torchaudio,transformers,aiohttp,yarl,torchsde,kornia,spandrel,soundfile,sentencepiece,av;from av.codec import Codec;print(json.dumps({'torch':torch.__version__,'torch_file':torch.__file__,'vp9':Codec('libvpx-vp9','w').name}))"
 check=subprocess.run([str(python),'-c',probe],capture_output=True,text=True,env=env,timeout=45)
 result['imports_returncode']=check.returncode
 for line in check.stdout.splitlines():
  try:
   value=json.loads(line)
   if isinstance(value,dict):result.setdefault('imports',[]).append({k:v for k,v in value.items() if k in ('python','torch','torch_file','vp9')})
  except ValueError:pass
 for line in check.stderr.splitlines():
  match=re.match(r"ModuleNotFoundError: No module named '([A-Za-z0-9_.-]+)'",line)
  if match:result['missing_module']=match[1]
  if line.startswith(('ImportError:','RuntimeError:','AttributeError:')):
   result['import_error_class']=line.split(':',1)[0]
 return result
def main():
 request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
 if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):raise RuntimeError('HOLD_OWNER_CONTEXT')
 lock=os.open(ROOT/'state/owner_maintenance.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:emit('pc_helper_install',pc_helpers(request))
 finally:os.close(lock)
 for kind,fn in (
  ('chat_launch_source',launch_source),('chat_saved_qa_features',saved_qa),
  ('s03_recall_source',lambda:source_excerpt(SCRIPTS/'s03_memory.py',{'recall','recall_text','remember','store','add','write','ingest','search','search_memory','_conn'})),
  ('media_diagnostic',media_diagnostic)):
  try:emit(kind,fn())
  except Exception as exc:emit(kind,{'state':'DIAGNOSTIC_ERROR','reason':safe_code(exc)})
 fixtures=[('minimal_math',[{'role':'user','content':'Сколько будет 17 умножить на 19? Ответь только числом.'}],323),
  ('minimal_resource',[{'role':'system','content':'Отвечай точно по инструкции пользователя.'},{'role':'user','content':'Из 32 ГБ занято 21 ГБ, ещё 3 ГБ зарезервировано. Сколько ГБ свободно? Ответь только числом.'}],8),
  ('minimal_history',[{'role':'user','content':'Сколько будет 17 умножить на 19? Ответь только числом.'},{'role':'assistant','content':'323'},{'role':'user','content':'Какое число ты только что получил? Ответь только этим числом.'}],323)]
 for name,messages,expected in fixtures:
  try:emit('chat_direct_fixture',model_case(name,messages,expected))
  except Exception as exc:emit('chat_direct_fixture',{'case':name,'state':'DIAGNOSTIC_ERROR','reason':safe_code(exc)})
 print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as exc:emit('followup_failed',{'reason':safe_code(exc)});raise SystemExit(2)
