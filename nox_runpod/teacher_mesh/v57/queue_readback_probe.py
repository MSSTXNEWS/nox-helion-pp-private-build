"""NOX V57: existing tool gateway queue discovery with GET only; never enqueue."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,re,urllib.request,urllib.error
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V57_GATEWAY_QUEUE_READ_ONLY_V1')
base='http://127.0.0.1:8095'
try:
    with urllib.request.urlopen(base+'/openapi.json',timeout=4) as r:data=json.loads(r.read(120000))
    paths=data.get('paths',{})
    if not isinstance(paths,dict):raise ValueError('paths')
except Exception:
    raise SystemExit('HOLD_GATEWAY_OPENAPI')
matches=[]
for path,ops in paths.items():
    if 'queue' in path.lower() and isinstance(ops,dict):
        methods=[x.upper() for x in ops if x.lower() in ('get','post','put','delete','patch')]
        matches.append((path,methods))
print('NATIVE_EXISTING_QUEUE_ROUTE_COUNT='+str(len(matches)))
for path,methods in matches[:5]:
    if not isinstance(path,str) or len(path)>110 or not path.startswith('/'):
        continue
    print('NATIVE_EXISTING_QUEUE_METHODS='+','.join(methods))
    # Do not print route or endpoint path in public GitHub logs.
    if 'GET' not in methods or '{' in path or '}' in path:
        print('NATIVE_EXISTING_QUEUE_READBACK=HOLD_NO_SIMPLE_GET')
        continue
    url=base+path
    try:
        req=urllib.request.Request(url,headers={'Accept':'application/json'},method='GET')
        with urllib.request.urlopen(req,timeout=5) as response:
            status=response.status
            payload=response.read(150000)
        print('NATIVE_EXISTING_QUEUE_READBACK_HTTP='+str(status))
        body=json.loads(payload)
        if isinstance(body,dict):
            print('NATIVE_EXISTING_QUEUE_RESPONSE_KEYS='+','.join(
                k for k in body.keys() if re.fullmatch('[a-zA-Z0-9_]{1,70}',k)))
            for key in ('pending','running','done','failed','completed','jobs','tasks','queue'):
                if key not in body:continue
                val=body[key]
                if isinstance(val,(list,tuple)):
                    print('NATIVE_EXISTING_QUEUE_'+key.upper()+'_COUNT='+str(len(val)))
                elif type(val) is int:
                    print('NATIVE_EXISTING_QUEUE_'+key.upper()+'_VALUE='+str(val))
        print('NATIVE_QUEUE_NATIVE_TASK_IDS_READBACK_VERIFIED=false')
    except urllib.error.HTTPError as e:
        print('NATIVE_EXISTING_QUEUE_READBACK_HTTP='+str(e.code))
    except (OSError,ValueError,TimeoutError):
        print('NATIVE_EXISTING_QUEUE_READBACK=HOLD')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=="__main__":
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as exc:
        print("NOX_V57_AUDIT="+str(exc) if str(exc).startswith("HOLD_") else "NOX_V57_AUDIT=HOLD")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print('NOX_V57_SSH_CLEANUP=HOLD')
            ok=False
    raise SystemExit(0 if ok else 2)
