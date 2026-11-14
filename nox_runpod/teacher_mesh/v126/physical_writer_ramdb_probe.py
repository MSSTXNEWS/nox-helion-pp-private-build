"""V126 physical original S03 remember() test in ephemeral RAM DB only.

Uses original server's s03_memory.remember with explicit db=TEMP. Never
opens actual user S03 for writing. Data is synthetic and disposed of.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE=r"""
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib,json,sqlite3,tempfile,uuid
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V126_RAMDB_SCHEMA=ORIGINAL_S03_NATIVE_REMEMBER_ISOLATED_V1')
import s03_memory
p=Path(s03_memory.__file__)
expected='82c592ea5a59281fb5fc1061d133ac4e149b8e95a6d0947a254882715cba7f91'
if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
 raise RuntimeError('HOLD_ORIGINAL_S03_SOURCE_DRIFT')
ram=Path('/dev/shm')
if not ram.is_dir():raise RuntimeError('HOLD_TMPFS_UNAVAILABLE')
t='NOX-V126-SYNTHETIC-MATH:'+uuid.uuid4().hex+':17x19=323'
m={'fact_key':'V126-ISOLATED-MATH','owner':'nox-single-owner','origin':'NOX_V126_TEMP_TEST',
   'valid_from':'2026-11-15T00:00:00+00:00','source_sha256':hashlib.sha256(t.encode()).hexdigest()}
try:
 with tempfile.TemporaryDirectory(prefix='nox-v126-',dir=ram) as d:
  path=Path(d)/'isolated.sqlite'
  result=s03_memory.remember(text=t,segment='M2',provenance='NOX-V126-SYNTHETIC',
      salience=.65,meta=m,db=path)
  if not path.is_file():raise RuntimeError('HOLD_NATIVE_WRITER_DID_NOT_USE_TEMP_DB')
  with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=3) as cx:
   cx.execute('PRAGMA query_only=ON')
   rows=cx.execute('SELECT id,segment,text,provenance,sha256,meta FROM s03_items').fetchall()
   integrity=cx.execute('PRAGMA quick_check').fetchone()[0]
  if len(rows)!=1 or integrity!='ok':raise RuntimeError('HOLD_TEMP_S03_INTEGRITY')
  row=rows[0]
  equal={'segment':row[1]=='M2','content':row[2]==t,
         'provenance':row[3]=='NOX-V126-SYNTHETIC',
         'sha256':row[4]==m['source_sha256']}
  print('NATIVE_V126_COMPARISON='+json.dumps(equal,sort_keys=True,separators=(',',':')))
  if not all(equal.values()):
   raise RuntimeError('HOLD_ORIGINAL_S03_WRITER_SEMANTICS')
  stored=json.loads(row[5])
  if stored.get('fact_key')!=m['fact_key'] or stored.get('source_sha256')!=m['source_sha256']:
   raise RuntimeError('HOLD_ORIGINAL_META_ENCODING')
 print('NATIVE_V126_TEMPDB='+json.dumps({
  'state':'ORIGINAL_REMEMBER_TEMP_RAM_DB_PASS',
  'native_writer_source_sha256':expected,'original_s03_writes':False,
  'row_count':1,'row_sha_matches':True,'meta_roundtrip':True,'temp_db_deleted':True,
  'native_writer_return_type':type(result).__name__},separators=(',',':')))
except Exception as ex:
 reason=str(ex)
 print('NATIVE_V126_TEMPDB='+json.dumps({'state':reason if reason.startswith('HOLD_') else 'HOLD_TEMP_WRITER',
  'original_s03_writes':False,'error_type':type(ex).__name__},separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    ssh.REMOTE=REMOTE
    original=ssh.api
    def retry(method,path,key,data=None):
        for i in range(4):
            try:
                result=original(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return result
            except RuntimeError as exc:
                if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=retry
    output=io.StringIO();good=False
    try:
        with contextlib.redirect_stdout(output):good=ssh.probe()
    except Exception as exc:
        value=str(exc)
        print('NOX_V126_RAM_TRANSPORT_HOLD='+(value if value.startswith('HOLD_') else 'SSH_TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(output):
                if not ssh.cleanup():good=False
        except Exception:good=False
    lines=output.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V126_TEMPDB=','TEMP_SSH_CLEANUP=')) and len(line)<800:
            print(line)
    accepted=(good and len([l for l in lines if l.startswith('NATIVE_V126_TEMPDB=')])==1
        and 'ORIGINAL_REMEMBER_TEMP_RAM_DB_PASS' in output.getvalue()
        and 'NATIVE_READ_ONLY_COMPLETE=true' in output.getvalue())
    print('NOX_V126_ORIGINAL_WRITER_TEMPDB='+('PASS' if accepted else 'HOLD'))
    return 0 if accepted else 2
if __name__=='__main__':
    raise SystemExit(main())
