"""Read-only schema/signature probe on the EXISTING NOX OneHost.

No private memory rows, owner passwords, cookies or file contents leave Vast.
This does not create a service, modify weights, touch S03 or change training.
"""
from __future__ import annotations
import contextlib
import io
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

ORIGINAL = ssh.api

def api(method, path, key, data=None):
    v=ORIGINAL(method,path,key,data)
    if method=='POST' and path.endswith('/ssh/'):
        time.sleep(12)
    return v

REMOTE = r"""
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib
import inspect
import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V125_SCHEMA=EXISTING_S03_FUNCTION_CONTRACT_READONLY_V1')
def emit(kind, **data):
    out=json.dumps(data,sort_keys=True,separators=(',',':'))
    if len(out)<650:print('NATIVE_V125_'+kind+'='+out)
def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() and not p.is_symlink() else None
def health(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:
            return r.status
    except Exception:return 0
import s03_memory
fn=s03_memory.remember
sig=inspect.signature(fn)
arguments=[]
for name,parameter in sig.parameters.items():
    arguments.append({'name':name,'kind':parameter.kind.name,
                      'has_default':parameter.default is not inspect.Parameter.empty})
emit('REMEMBER',arguments=arguments,is_callable=callable(fn))
root=Path(s03_memory.DB)
if not root.is_file() or root.is_symlink():
    raise RuntimeError('HOLD_ORIGINAL_S03_DB_FILE')
with sqlite3.connect('file:'+str(root)+'?mode=ro',uri=True,timeout=3) as con:
    con.execute('PRAGMA query_only=ON')
    tables=[row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    cols=[{'name':row[1],'type':row[2],'nullable':not bool(row[3]),'primary_key':bool(row[5])}
          for row in con.execute("PRAGMA table_info(s03_items)")]
    integrity=con.execute('PRAGMA quick_check').fetchone()[0]
emit('TABLES',names=[name for name in tables if name in (
    's03_items','nox_v29_dialogs','nox_v29_dialog_messages')],has_s03_items='s03_items' in tables,
    quick_check_ok=(integrity=='ok'))
emit('COLUMNS',columns=cols[:18])
base=Path('/root/nox/scripts')
emit('SOURCE',proxy_sha256=digest(base/'chat_proxy.py'),
    bridge_sha256=digest(base/'nox_v29_chat_bridge.py'),
    proxy_http=health(8080),model_http=health(8081),
    nox_writes=False,stop_active=any(Path(p).exists() for p in (
      '/root/nox/STOP','/root/nox/STOP.flag','/workspace/NOX_STOP')))
proxy_source=(base/'chat_proxy.py').read_text(encoding='utf8')
emit('ANCHORS',
     v120_registrations=proxy_source.count('register_nox_v120_s03_memory_views(app, globals())'),
     owner_auth_scope_matches=proxy_source.count(
       "'/api/nox/history','/api/nox/experience','/api/training/status'"),
     already_fact_bound=('register_nox_v125_owner_fact_write(' in proxy_source),
     external_source_text_logged=False)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    ssh.REMOTE=REMOTE
    ssh.api=api
    out=io.StringIO()
    attached=False
    cleanup=False
    try:
        with contextlib.redirect_stdout(out):attached=ssh.probe()
    except Exception:
        print('NOX_V125=HOLD_NATIVE_CONNECTION')
    finally:
        try:
            with contextlib.redirect_stdout(out):cleanup=ssh.cleanup()
        except Exception:cleanup=False
    rows=[]
    for line in out.getvalue().splitlines():
        if line.startswith(('NATIVE_V125_REMEMBER=','NATIVE_V125_TABLES=',
                             'NATIVE_V125_COLUMNS=','NATIVE_V125_SOURCE=',
                             'NATIVE_V125_ANCHORS=')) and len(line)<760:
            print(line);rows.append(line)
        if line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:120])
    good=bool(attached and cleanup and
              {'NATIVE_V125_REMEMBER','NATIVE_V125_TABLES',
               'NATIVE_V125_COLUMNS','NATIVE_V125_SOURCE',
               'NATIVE_V125_ANCHORS'} ==
              {s.split('=',1)[0] for s in rows})
    print('NOX_V125_S03_CONTRACT_READONLY='+('PASS' if good else 'HOLD'))
    return 0 if good else 2

if __name__=='__main__':
    raise SystemExit(main())
