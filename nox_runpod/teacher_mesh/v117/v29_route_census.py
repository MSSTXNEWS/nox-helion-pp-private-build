"""V117: all 92 WEB V29.3 routes vs actual OneHost route registration.

Read only. Does NOT claim that route presence == functional E2E.
No model request, source writing, GPU changes, credentials, memory read or deletion.
"""
from __future__ import annotations
import contextlib,io,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib,json,re
from pathlib import Path
from fastapi.routing import APIRoute
from starlette.routing import Mount
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V117_REAL_V29_ROUTE_CENSUS_V1')
site=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site')
if not site.is_dir():raise SystemExit('HOLD_ORIGINAL_SITE')
paths={}
for f in sorted(site.iterdir()):
 if f.suffix not in ('.js','.mjs') or not f.is_file() or f.is_symlink():continue
 raw=f.read_text(errors='replace')
 for found in re.finditer(r"""[\"'](/(?:api|v1)/[a-zA-Z0-9_/?={}&.\-]+)[\"']""",raw):
  path=found.group(1).split('?',1)[0]
  paths.setdefault(path,set()).add(f.name)
import chat_proxy
from fastapi.routing import APIRoute
api_routes=[r for r in chat_proxy.app.routes if isinstance(r,APIRoute)]
mounts=[r.path for r in chat_proxy.app.routes if isinstance(r,Mount)]
matched=[]
unbound=[]
for path in sorted(paths):
 found=[r for r in api_routes if bool(r.path_regex.match(path))]
 if found:
  matched.append(path)
  report={'route':path,'registration':'DIRECT','method_candidates':sorted(set(
    method for r in found for method in r.methods)),
    'handler_names':sorted(set(r.endpoint.__name__ for r in found))[:5]}
 else:
  unbound.append(path)
  report={'route':path,'registration':'NO_DIRECT_ROUTE',
          'possible_dynamic_or_upstream':True}
 print('NATIVE_V117_ROUTE='+json.dumps(report,ensure_ascii=False,separators=(',',':')))
summary={'unique_web_literal_api_references':len(paths),
 'registered_exact_or_pattern':len(matched),
 'not_registered_directly':len(unbound),
 'first_party_source_sha256':hashlib.sha256((site/'nox-chat.js').read_bytes()).hexdigest(),
 'app_api_route_count':len(api_routes),'app_mount_paths':mounts[:15],
 'functional_e2e_passed_this_audit':0,
 'all_92_functions_operational':False,
 'production_web_switch_allowed_by_this_audit':False,
 'read_only':True}
print('NATIVE_V117_SUMMARY='+json.dumps(summary,ensure_ascii=False,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    ssh.REMOTE=REMOTE
    old=ssh.api
    def gate(method,path,key,data=None):
        for i in range(4):
            try:
                v=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return v
            except RuntimeError as e:
                if method!='GET' or str(e)!='HOLD_VAST_API_HTTP_429' or i==3:raise
                time.sleep((10,20,40)[i])
    ssh.api=gate
    captured=io.StringIO();okay=False
    try:
        with contextlib.redirect_stdout(captured):okay=ssh.probe()
    except Exception as e:
        message=str(e)
        print('NOX_V117_HOLD='+(message if message.startswith('HOLD_') else 'CONNECTION'))
    finally:
        try:
            with contextlib.redirect_stdout(captured):
                if not ssh.cleanup():okay=False
        except Exception:okay=False
    summaries=[]
    for line in captured.getvalue().splitlines():
        if line.startswith('NATIVE_V117_SUMMARY=') and len(line)<1200:
            print(line);summaries.append(line)
        elif line.startswith('NATIVE_V117_ROUTE=') and len(line)<700:
            print(line)
        elif line.startswith('TEMP_SSH_CLEANUP='):
            print(line[:110])
    print('NOX_V117_NATIVE_AUDIT_PASS='+str(bool(okay and len(summaries)==1)).lower())
    return 0 if okay and len(summaries)==1 else 2
if __name__=='__main__':raise SystemExit(main())

# V117 audit requested again after verified V114/V116 owner WEB E2E; read-only.
