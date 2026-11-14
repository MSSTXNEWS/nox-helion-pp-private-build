"""V80: read-only S03 inventory while Resonance is degraded.
No private record values leave Vast. No new database, worker or weights.
"""
from __future__ import annotations
import contextlib,io
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as bridge
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import sqlite3, json, os, re, hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V80_S03_MEMORY_INVENTORY_V1')
dbs=[('SEED','/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3'),
('INFINITE','/root/nox/memory/infinite/nox_infinite_memory.sqlite3'),
('COPY','/root/nox/memory/pc_t809u/nox_seed_memory.sqlite3')]
total=0
for label,source in dbs:
 p=Path(source)
 info={'label':label,'present':False,'read_only':True}
 try:
  if not p.is_file() or p.is_symlink():raise ValueError('MISSING_OR_SYMLINK')
  size=p.stat().st_size
  if size>200_000_000:raise ValueError('SIZE_GATE')
  info.update(present=True,size_bytes=size)
  # Read-only mode includes a current committed WAL view; never make an immutable
  # claim or alter / delete SQLite files.
  with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=3) as con:
   con.execute('PRAGMA query_only=ON')
   good=con.execute('PRAGMA quick_check').fetchone()[0]
   tables=[str(v[0]) for v in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 100")]
   safe=[t for t in tables if re.fullmatch('[A-Za-z0-9_]{1,70}',t)]
   info['quick_check_ok']=good=='ok'
   info['tables']=len(safe)
   counts={}
   for t in safe:
    if any(key in t.casefold() for key in ('memory','fact','segment','genesis','brain_node','brain_edge','skill','message','event','learning')):
     try:counts[t]=int(con.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0])
     except sqlite3.DatabaseError:pass
   info['row_counts']=counts
   public_schema={}
   for t in safe:
    if t in ('s03_segments','genesis_ledger','facts','brain_nodes','brain_edges','memory_marks'):
     try:
      cols=[str(row[1]) for row in con.execute('PRAGMA table_info("'+t+'")') if re.fullmatch('[A-Za-z0-9_]{1,70}',str(row[1]))]
      public_schema[t]=cols[:35]
     except sqlite3.DatabaseError:pass
   info['column_names_only']=public_schema
   total+=sum(counts.values())
 except Exception as e:info['hold']=type(e).__name__
 print('NATIVE_S03_DATABASE='+json.dumps(info,separators=(',',':'),sort_keys=True))
print('NATIVE_S03_DISCOVERED_ROW_COUNTS_SUM='+str(total))
print('NATIVE_S03_PRIVATE_RECORD_VALUES_EXPORTED=false')
print('NATIVE_TRAIN_DATASET_GENERATED=false')
print('NATIVE_MEMORY_WRITES_PERFORMED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    out=io.StringIO();ok=False
    try:
        bridge.REMOTE=REMOTE
        with contextlib.redirect_stdout(out):
            ok=bridge.probe()
    except Exception as exc:
        msg=str(exc)
        print('NOX_V80_HOLD='+(msg if msg.startswith('HOLD_') and len(msg)<80 else 'SSH_OR_NATIVE'))
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if bridge.cleanup() is not True:ok=False
        except Exception:ok=False
    data=out.getvalue()
    for line in data.splitlines():
        if line.startswith(('NATIVE_S03_','NATIVE_MEMORY_','NATIVE_TRAIN_','NATIVE_READ_ONLY_','TEMP_SSH_CLEANUP=')) and len(line)<2500:
            print(line)
    passed=bool(ok and 'NATIVE_READ_ONLY_COMPLETE=true' in data and 'NATIVE_S03_DATABASE=' in data)
    print('NOX_V80_S03_INVENTORY_VERIFIED='+str(passed).lower())
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
