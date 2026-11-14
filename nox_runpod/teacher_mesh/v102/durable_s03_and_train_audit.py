"""V102: durable S03 acceptance in separate process + existing teacher and trainer evidence.
Read-only, no private content, no edits to models or supervisor state.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,sqlite3,json,subprocess,time,hashlib,stat,re,urllib.request
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V102_S03_EXTERNAL_PROCESS_AND_TRAINER_ROLES_V1')
def emit(k,obj):
 s=json.dumps(obj,sort_keys=True,separators=(',',':'))
 if len(s)<3500:print('NATIVE_V102_'+k+'='+s)
paths=[('seed','/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'),
 ('infinite','/root/nox/memory/infinite/nox_infinite_memory.sqlite3')]
for name,path in paths:
 p=Path(path)
 result={'db':name,'present':p.is_file(),'read_only':True,'exact_private_text_exported':False}
 try:
  if not p.is_file() or p.is_symlink():raise RuntimeError('HOLD_DB_PATH')
  with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=3) as con:
   con.execute('PRAGMA query_only=ON')
   tables={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
   counts={}
   for table in ('chat_messages','s03_segments','messages','facts','memory_marks'):
    if table not in tables:continue
    cols={x[1].lower():x[1] for x in con.execute('PRAGMA table_info("'+table+'")')}
    names=[cols[c] for c in ('content','text','message','user_text','answer','value','payload') if c in cols]
    matches=0
    for c in names[:6]:
     matches+=int(con.execute('SELECT COUNT(*) FROM "'+table+'" WHERE CAST("'+c+'" AS TEXT) LIKE ?',('%N100S03CYCLE%',)).fetchone()[0])
    counts[table]={'marker_match_fields_sum':matches,'rows':int(con.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0])}
   result['tables']=counts
   result['quick_check_ok']=con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
 except Exception as e:result['hold']=type(e).__name__
 emit('CROSS_PROCESS_S03',result)
# Confirm the REAL database used by s03_memory from a different process.
try:
 import sys
 sys.path.insert(0,'/root/nox/scripts')
 import s03_memory
 db=Path(s03_memory.DB)
 result={'db_basename':db.name[:80],'present':db.is_file(),'read_only':True}
 if db.is_file() and not db.is_symlink():
  with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=4) as con:
   con.execute('PRAGMA query_only=ON')
   tables={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
   fields={}
   for table in ('s03_segments','chat_messages','messages','memories','memory','segments'):
    if table not in tables:continue
    cols={r[1].lower():r[1] for r in con.execute('PRAGMA table_info("'+table+'")')}
    matches=0
    for cname in ('content','text','message','user_text','answer','value','payload'):
     if cname in cols:
      matches+=int(con.execute('SELECT COUNT(*) FROM "'+table+'" WHERE CAST("'+cols[cname]+'" AS TEXT) LIKE ?',('%N100S03CYCLE%',)).fetchone()[0])
    fields[table]=matches
   result['synthetic_marker_matches_by_table']=fields
   result['quick_check_ok']=con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
   result['table_names']=[x for x in sorted(tables) if not x.startswith('sqlite_')][:25]
   result['columns_metadata']={}
   for table in sorted(tables):
    if any(word in table.casefold() for word in ('segment','message','memory','knowledge','fact','turn','record')):
     result['columns_metadata'][table]=[row[1] for row in con.execute('PRAGMA table_info("'+table.replace('"','')+'")')][:14]
     if len(result['columns_metadata'])>=6:break
 emit('NATIVE_S03_FILE',result)
except Exception as e:emit('NATIVE_S03_FILE',{'state':'HOLD_NATIVE_S03_FILE_READ','error_type':type(e).__name__})

# Actual running trainer process / source family and existence of data are sampled
# via numeric metadata; no logs, prompts or private files are exported.
svc={}
for name in ('nox-train-volta-t866u','nox-teacher-serve-t811u','nox-agent-tuner-t858u'):
 try:
  p=subprocess.run(['supervisorctl','status',name],text=True,capture_output=True,timeout=7)
  args=p.stdout.strip().split()
  svc[name]={'state':args[1] if p.returncode==0 and len(args)>1 else 'UNKNOWN',
             'supervisor_pid':int(args[3].rstrip(',')) if len(args)>3 and args[2]=='pid' and args[3].rstrip(',').isdigit() else None}
 except Exception:svc[name]={'state':'UNKNOWN'}
emit('SERVICES',svc)
# Broader categorised index: no raw file paths or user data in logs.
roots=[Path('/root/nox'),Path('/root/.cache/huggingface/hub'),Path('/workspace')]
grouped={};count=0;start=time.monotonic();limit_hit=False
SKIP={'.git','node_modules','__pycache__','venv','.venv','images','assets','static','screenshots','logs','tmp','temp','dist','build'}
for base in roots:
 if not base.is_dir():continue
 for directory,dirs,files in os.walk(base,followlinks=False):
  if time.monotonic()-start>22 or count>35000:
   limit_hit=True;break
  count+=1
  depth=len(Path(directory).relative_to(base).parts)
  dirs[:]=[x for x in dirs if depth<8 and x not in SKIP and not (Path(directory)/x).is_symlink()][:110]
  p=Path(directory)
  bucket=(p.relative_to(base).parts or ('ROOT',))[0][:45]
  key=base.name+'/'+bucket
  for file in files:
   if file.endswith(('.safetensors','.gguf','.pt','.pth','.bin','.parquet','.jsonl')):
    try:
     item=p/file;st=item.stat()
     if not stat.S_ISREG(st.st_mode):continue
     kind=('safetensors' if file.endswith('.safetensors') else 'gguf' if file.endswith('.gguf') else
           'jsonl' if file.endswith('.jsonl') else 'parquet' if file.endswith('.parquet') else 'torch_other')
     row=grouped.setdefault(key,{'safetensors':0,'gguf':0,'jsonl':0,'parquet':0,'torch_other':0,'weights_bytes':0})
     row[kind]+=1
     if kind in ('safetensors','gguf','torch_other'):row['weights_bytes']+=st.st_size
    except Exception:pass
_totals={kind:sum(entry.get(kind,0) for entry in grouped.values()) for kind in ('safetensors','gguf','jsonl','parquet','torch_other','weights_bytes')}
emit('STORAGE_SUMMARY',{'dirs_seen':count,'scan_limited':limit_hit,'storage_buckets':len(grouped),'totals':_totals})
for _bucket in sorted(({'storage_bucket':k,**v} for k,v in grouped.items()),key=lambda x:-x['weights_bytes'])[:12]:
 emit('STORAGE_BUCKET',_bucket)
# Safe source-level indicators only; 'running' by supervisor is not proof of optimizer work.
for path in ('/root/nox/scripts/train_qlora_35b_t866u.py','/root/nox/scripts/train_worm_t811u.py'):
 p=Path(path)
 if not p.is_file():continue
 raw=p.read_bytes()
 emit('TRAINER_TYPE',{'name':p.name,'sha256':hashlib.sha256(raw).hexdigest(),
                     'uses_peft':b'peft' in raw.lower(),
                     'has_lora':b'lora' in raw.lower()})
print('NATIVE_V102_TEXT_OR_KEYS_EXPORTED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 out=io.StringIO();okay=False;ssh.REMOTE=REMOTE
 old=ssh.api
 def gate(method,path,key,data=None):
  for i in range(4):
   try:
    result=old(method,path,key,data)
    if method=="POST" and path.endswith('/ssh/'):time.sleep(12)
    return result
   except RuntimeError as e:
    if method!="GET" or str(e)!="HOLD_VAST_API_HTTP_429" or i==3:raise
    time.sleep((10,20,40)[i])
 ssh.api=gate
 try:
  with contextlib.redirect_stdout(out):okay=ssh.probe()
 except Exception as e:
  v=str(e);print('NOX_V102_HOLD='+(v if v.startswith('HOLD_') and len(v)<90 else 'SSH'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:okay=False
  except Exception:okay=False
 lines=[]
 for line in out.getvalue().splitlines():
  if line.startswith(('NATIVE_V102_','TEMP_SSH_CLEANUP=')):
   print(line[:3600]);lines.append(line)
 passed=bool(okay and any(x.startswith('NATIVE_V102_CROSS_PROCESS_S03=') for x in lines) and
              any(x.startswith('NATIVE_V102_STORAGE_SUMMARY=') for x in lines) and
              'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
 print('NOX_V102_PHYSICAL_METADATA_ACCEPTED='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
