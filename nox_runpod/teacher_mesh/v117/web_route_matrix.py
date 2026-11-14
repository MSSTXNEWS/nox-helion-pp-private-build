"""V117 read-only inventory: real 92 WEB routes vs existing OneHost app.

Reads frozen source matrix in GitHub Actions runner; imports existing NOX app
on the Vast host in its native venv to list registered route names.
No calls to user endpoints, no passwords, private records or model generation.
"""
from __future__ import annotations
import base64
import contextlib
import io
import json
from pathlib import Path
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

MATRIX=Path('coordination/NOX_V98_WEB_FULL_REAL_API_MATRIX.json')
REMOTE_TEMPLATE=r'''
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import base64,json,hashlib
from collections import Counter
from fastapi.routing import APIRoute
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V117_WEB_92_EXISTING_NATIVE_ROUTES_V1')
expected=json.loads(base64.b64decode('___EXPECTED_ROUTES_B64___').decode('utf8'))
if len(expected)!=92 or len(set(expected))!=92:
 raise RuntimeError('HOLD_FRONTEND_MATRIX_COUNT')
proxy=Path('/root/nox/scripts/chat_proxy.py')
import chat_proxy
api={r.path for r in chat_proxy.app.routes if isinstance(r,APIRoute)}
matched=sorted(set(expected)&api)
missing=sorted(set(expected)-api)
groups=Counter()
for name in expected:
 parts=name.strip('/').split('/')
 key=(parts[1] if len(parts)>1 else 'unknown')
 if key=='ui' and len(parts)>2:key='ui/'+parts[2]
 groups[key]+=1
print('NATIVE_V117_ROUTE_SCOPE='+json.dumps({'runtime':'CURRENT_EXISTING_ONEHOST_FASTAPI','expected':len(expected),'matched':len(matched),'unmapped':len(missing),'no_mock_pass_claims':True},sort_keys=True,separators=(',',':')))
print('NATIVE_V117_ROUTE_SUMMARY='+json.dumps({'expected':len(expected),
 'native_direct_match':len(matched),'no_direct_route':len(missing),
 'registered_native_api_routes':len(api),
 'src_sha256':hashlib.sha256(proxy.read_bytes()).hexdigest()},sort_keys=True,separators=(',',':')))
print('NATIVE_V117_NATIVE_MATCHES='+json.dumps(matched,separators=(',',':')))
method_info=[{'path':r.path,'methods':sorted(r.methods)} for r in chat_proxy.app.routes if isinstance(r,APIRoute) and r.path in set(expected)]
for offset in range(0,len(method_info),5):
 print('NATIVE_V117_ROUTE_METHODS_'+str(offset//5)+'='+json.dumps(method_info[offset:offset+5],separators=(',',':')))
for n in range(0,len(api),9):
 print('NATIVE_V117_NATIVE_ROUTE_PART_'+str(n//9)+'='+json.dumps(sorted(api)[n:n+9],separators=(',',':')))
print('NATIVE_V117_MISSING_EXAMPLES='+json.dumps(missing[:60],separators=(',',':')))
print('NATIVE_V117_GROUP_COUNTS='+json.dumps(groups,sort_keys=True,separators=(',',':')))
def group(path):
 parts=path.strip('/').split('/')
 return parts[1] if len(parts)>1 else 'unknown'
missing_groups=Counter(group(x) for x in missing)
matched_groups=Counter(group(x) for x in matched)
print('NATIVE_V117_MATCHED_GROUPS='+json.dumps(matched_groups,sort_keys=True,separators=(',',':')))
print('NATIVE_V117_MISSING_GROUPS='+json.dumps(missing_groups,sort_keys=True,separators=(',',':')))
bridge=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
print('NATIVE_V117_CURRENT_SHAS='+json.dumps({
 'proxy_sha256':hashlib.sha256(proxy.read_bytes()).hexdigest(),
 'bridge_sha256':hashlib.sha256(bridge.read_bytes()).hexdigest() if bridge.is_file() else None,
 'registration_only_not_functional_e2e':True},sort_keys=True,separators=(',',':')))
print('NATIVE_V117_PRIVATE_RECORDS_EXPORTED=false')
print('NATIVE_V117_SERVICES_RESTARTED=false')
print('NATIVE_V117_WEIGHTS_CHANGED=false')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
'''
def main():
    data=json.loads(MATRIX.read_text(encoding='utf8'))
    routes=sorted(str(p['route']) for p in data['functions'])
    assert len(routes)==92 and len(set(routes))==92
    ssh.REMOTE=REMOTE_TEMPLATE.replace('___EXPECTED_ROUTES_B64___',
        base64.b64encode(json.dumps(routes,separators=(',',':')).encode()).decode())
    old=ssh.api
    def safe(method,path,key,data=None):
        for attempt in range(4):
            try:
                v=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return v
            except RuntimeError as ex:
                if method!='GET' or str(ex)!='HOLD_VAST_API_HTTP_429' or attempt==3:raise
                time.sleep((10,20,40)[attempt])
    ssh.api=safe
    out=io.StringIO();ok=False
    try:
        with contextlib.redirect_stdout(out):ok=ssh.probe()
    finally:
        try:
            with contextlib.redirect_stdout(out):
                if ssh.cleanup() is not True:ok=False
        except Exception:ok=False
    lines=out.getvalue().splitlines()
    for l in lines:
        if l.startswith(('NATIVE_V117_','TEMP_SSH_CLEANUP=')) and len(l)<13000:
            print(l)
    passed=bool(ok and any(l.startswith('NATIVE_V117_ROUTE_SUMMARY=') for l in lines)
                and 'NATIVE_READ_ONLY_COMPLETE=true' in out.getvalue())
    print('NOX_V117_NATIVE_ROUTE_INVENTORY_ACCEPTED='+str(passed).lower())
    return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
