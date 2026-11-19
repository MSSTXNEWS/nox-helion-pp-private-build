"""NOX V54: native read-only runtime process <-> S03 <-> HTTP binding audit.

No personal DB records, shell script bodies, API credentials or chat contents
are collected. Reuses authorized temporary SSH from V51, with verified detach.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,sys,sqlite3,hashlib,ast,datetime,http.client,json,socket
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V54_RUNTIME_BINDINGS_READONLY_V1')
memory=[
 '/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3',
 '/root/nox/memory/infinite/nox_infinite_memory.sqlite3',
 '/root/nox/memory/pc_t809u/nox_seed_memory.sqlite3',
]
for i,path in enumerate(memory,1):
    p=Path(path);label='NATIVE_DB_'+str(i)
    if not p.is_file():print(label+'_PRESENT=false');continue
    print(label+'_PRESENT=true')
    print(label+'_SIZE_BYTES='+str(p.stat().st_size))
    print(label+'_MTIME_UTC='+datetime.datetime.fromtimestamp(
        p.stat().st_mtime,datetime.timezone.utc).isoformat())
    try:
        print(label+'_SHA256='+hashlib.sha256(p.read_bytes()).hexdigest())
    except OSError:
        print(label+'_SHA256=HOLD')
    # Read-only immutable metadata. No user chats or records inspected.
    try:
        con=sqlite3.connect('file:'+path+'?mode=ro&immutable=1',uri=True,timeout=.3)
        con.execute('PRAGMA query_only=ON')
        for table in ('genesis_ledger','s03_segments','self_state','messages','facts','brain_nodes','brain_edges'):
            valid=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
            if valid:
                q=con.execute('SELECT COUNT(*) FROM "'+table+'"')
                print(label+'_ROW_COUNT_'+table.upper()+'='+str(q.fetchone()[0]))
        con.close()
    except sqlite3.DatabaseError:
        print(label+'_SQLITE_READ=HOLD')
# File descriptors: determine which SQLite DB is physically opened by any live process.
targets=[str(Path(x).resolve()) for x in memory]
fdseen={x:set() for x in targets}
for proc in os.listdir('/proc'):
    if not proc.isdigit():continue
    fd=Path('/proc')/proc/'fd'
    try:items=list(fd.iterdir())[:160]
    except (OSError,PermissionError):continue
    for f in items:
        try:dst=os.readlink(f)
        except OSError:continue
        stripped=dst.removesuffix(' (deleted)')
        for target in targets:
            if stripped==target or stripped in (target+'-wal',target+'-shm'):
                fdseen[target].add(int(proc))
for i,folder in enumerate(targets,1):
    pids=sorted(fdseen[folder])
    print('NATIVE_DB_'+str(i)+'_OPEN_PROCESS_COUNT='+str(len(pids)))
    print('NATIVE_DB_'+str(i)+'_OPEN_PIDS='+json.dumps(pids[:18]))
# Structural inspection of source only: AST names, never strings or code.
sources={
    'dispatcher':'/root/nox/program/duty/dispatcher.py',
    'agent_loop':'/root/nox/scripts/agent_loop.py',
    'slim_chat':'/root/nox/scripts/slim_chat_t885u.py',
    'wiring_audit':'/root/nox/program/wiring_audit.py',
}
for label,path in sources.items():
    p=Path(path)
    if not p.is_file():print('NATIVE_SOURCE_'+label.upper()+'=ABSENT');continue
    try:
        text=p.read_text(encoding='utf-8',errors='replace')[:220000]
        tree=ast.parse(text)
        functions=[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        classes=[n.name for n in tree.body if isinstance(n,ast.ClassDef)]
        public=lambda x:[t for t in x if re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,65}',t)][:25]
        print('NATIVE_SOURCE_'+label.upper()+'_TOP_FUNCTIONS='+json.dumps(public(functions)))
        print('NATIVE_SOURCE_'+label.upper()+'_CLASSES='+json.dumps(public(classes)))
    except (OSError,SyntaxError):
        print('NATIVE_SOURCE_'+label.upper()+'=HOLD_AST')
# Bounded loopback HTTP (only GET, no auth, no body output).
ports=[8080,8081,8082,8084,8087,8088,8092,8093,8095,8384,8888,11111,11112]
for port in ports:
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=.9)
    try:
        conn.request('GET','/health',headers={'Accept':'application/json'})
        response=conn.getresponse()
        result=str(response.status)
        response.read(250)
    except (OSError,TimeoutError,http.client.HTTPException):
        result='UNAVAILABLE'
    finally:
        conn.close()
    print('NATIVE_HEALTH_HTTP_'+str(port)+'='+result)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as exc:
        print("NOX_V54_AUDIT="+str(exc) if str(exc).startswith("HOLD_") else "NOX_V54_AUDIT=HOLD")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print('NOX_V54_SSH_CLEANUP=HOLD')
            ok=False
    raise SystemExit(0 if ok else 2)
