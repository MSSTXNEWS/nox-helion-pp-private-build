"""V103: identify actual S03 SQLite receipt and full-parameter model files.
Read only tables, model index references and JSONL schema keys. No user text exported.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,sys,re,json,sqlite3,subprocess,hashlib,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V103_TRAINABLE_WEIGHTS_NATIVE_S03_RECEIPT_V1')
def emit(label,data):
 s=json.dumps(data,separators=(',',':'),sort_keys=True)
 if len(s)<1200:print('NATIVE_V103_'+label+'='+s)
sys.path.insert(0,'/root/nox/scripts')
try:
 import s03_memory
 path=Path(s03_memory.DB)
 state={'db_basename':path.name,'present':path.is_file(),'read_only':True,'private_data_exported':False}
 if path.is_file() and not path.is_symlink():
  with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=4) as con:
   con.execute('PRAGMA query_only=ON')
   state['integrity_ok']=con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
   names=[x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
   for table in ('s03_items','s03_ledger','chunks','docs'):
    if table not in names:continue
    columns=[x[1] for x in con.execute('PRAGMA table_info("'+table+'")')][:30]
    count=con.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0]
    matches=0
    teacher_matches=0
    for col in columns:
     if re.fullmatch('[A-Za-z0-9_]{1,80}',col) and any(x in col.lower() for x in ('content','text','value','answer','message','payload','meta','provenance','source')):
      matches+=int(con.execute('SELECT COUNT(*) FROM "'+table+'" WHERE CAST("'+col+'" AS TEXT) LIKE ?',('%N100S03CYCLE%',)).fetchone()[0])
      teacher_matches+=int(con.execute('SELECT COUNT(*) FROM "'+table+'" WHERE CAST("'+col+'" AS TEXT) LIKE ?',('%N107_TEACHER_LESSON_%',)).fetchone()[0])
    emit('S03_TABLE',{'table':table,'rows':count,'columns':columns,'synthetic_marker_matches_sum':matches,
      'local_teacher_marker_matches_sum':teacher_matches})
  emit('S03_FILE',state)
except Exception as e:emit('S03_FILE',{'state':'HOLD_SOURCE_OR_SQL','error_type':type(e).__name__})
# Larger restored progress packages can contain full weights without adjacent
# configuration; inspect structure and shard-index completeness without any load.
roots=[Path('/root/nox/progress_pull_t784u'),Path('/root/nox/models'),
 Path('/root/nox/progress_pull_pc_t809u'),Path('/root/nox/state'),
 Path('/root/nox/progress_a40_20261112T0458Z_step26')]
start=time.monotonic()
weights=[];datasets=[];models=0
for base in roots:
 if not base.is_dir():continue
 for directory,dirs,files in os.walk(base,followlinks=False):
  if time.monotonic()-start>19 or models>10000:break
  models+=1
  depth=len(Path(directory).relative_to(base).parts)
  dirs[:]=[x for x in dirs if depth<7 and x not in ('node_modules','.git','logs','tmp','cache','venv','.venv','__pycache__') and not (Path(directory)/x).is_symlink()][:80]
  p=Path(directory)
  shard_names=[v for v in files if v.endswith('.safetensors') or v.startswith('pytorch_model') and v.endswith('.bin')]
  if shard_names:
   size=sum((p/f).stat().st_size for f in shard_names if (p/f).is_file())
   indexes=[f for f in files if f.endswith('.safetensors.index.json') or f.endswith('pytorch_model.bin.index.json')]
   completeness='NO_INDEX'
   if indexes:
    try:
     data=json.loads((p/indexes[0]).read_text(encoding='utf8')[:2_000_000])
     mapping=data.get('weight_map') or {}
     needed={str(x) for x in mapping.values()}
     completeness='INDEX_ALL_REFERENCES_PRESENT' if needed and all((p/n).is_file() for n in needed) else 'INDEX_MISSING_SHARDS_OR_EMPTY'
    except Exception:completeness='INDEX_UNREADABLE'
   weights.append({'root':base.name[:40],'folder':p.name[:55],'shard_count':len(shard_names),
     'bytes':size,'has_config_json':(p/'config.json').is_file(),
     'index_status':completeness})
  for f in files:
   if not f.endswith('.jsonl') or len(datasets)>=18:continue
   fp=p/f
   try:
    if not fp.is_file() or fp.stat().st_size>2_000_000_000:continue
    with fp.open('rb') as stream:line=stream.readline(256_000)
    parsed=json.loads(line)
    keys=sorted(map(str,parsed.keys()))[:30] if isinstance(parsed,dict) else ['NON_OBJECT']
    datasets.append({'root':base.name[:40],'folder':p.name[:40],'file_basename':f[:55],
      'bytes':fp.stat().st_size,'first_record_keys':keys,'content_exported':False})
   except Exception:continue
for item in sorted(weights,key=lambda x:-x['bytes'])[:18]:emit('WEIGHT_SET',item)
for item in datasets[:12]:emit('JSONL_SCHEMA',item)
emit('INVENTORY_SUMMARY',{'dirs_seen':models,'weight_dirs':len(weights),'schema_checked_jsonl':len(datasets)})
# Observe last error classes only, never export logs or examples.
for base in (Path('/root/nox/logs'),Path('/root/nox/state')):
 if not base.is_dir():continue
 matches=list(base.glob('*volta*.log'))[:6]
 for file in matches:
  try:
   raw=file.open('rb').read()[-100000:].lower()
   emit('TRAIN_LOG_CLASS',{'basename':file.name[:75],
    'oom_occurrences':raw.count(b'out of memory')+raw.count(b'cuda oom'),
    'disk_full_occurrences':raw.count(b'no space left'),
    'optimizer_step_mentions':raw.count(b'optimizer step')})
  except Exception:pass
print('NATIVE_V103_NO_WEIGHTS_OR_DATA_MODIFIED=true')
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
  x=str(e);print('NOX_V103_HOLD='+(x if x.startswith('HOLD_') and len(x)<80 else 'SSH'))
 finally:
  try:
   with contextlib.redirect_stdout(out):
    if ssh.cleanup() is not True:okay=False
  except Exception:okay=False
 lines=[]
 for line in out.getvalue().splitlines():
  if line.startswith(('NATIVE_V103_','TEMP_SSH_CLEANUP=')):
   print(line[:1300]);lines.append(line)
 passed=bool(okay and any(x.startswith('NATIVE_V103_INVENTORY_SUMMARY=') for x in lines) and any(x.startswith('NATIVE_V103_S03_TABLE=') for x in lines) and 'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
 print('NOX_V103_SOURCE_AND_DB_INVENTORY_ACCEPTED='+str(passed).lower())
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
