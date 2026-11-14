"""V122 immutable native audit: current WEB bridge/proxy, 92 routes, S03, STOP and resources.

Only existing OneHost and temporary authorized SSH are used. Never write on
Vast except the short-lived SSH public-key registration handled by V51, whose
cleanup is required. Does not log records, owner secrets, or prompts.
"""
from __future__ import annotations
import base64, contextlib, io, json, time
from pathlib import Path
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

MATRIX = Path('coordination/NOX_V98_WEB_FULL_REAL_API_MATRIX.json')
REMOTE_TEMPLATE = r"""
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import base64,hashlib,json,os,sqlite3,subprocess,urllib.error,urllib.request
from pathlib import Path
from fastapi.routing import APIRoute
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_V122_SCHEMA=READ_ONLY_EXACT_REAL_WEB_ROUTES_V1')
proxy=Path('/root/nox/scripts/chat_proxy.py')
bridge=Path('/root/nox/scripts/nox_v29_chat_bridge.py')
catalog=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-function-catalog.js')
stops=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(path):
 if not path.is_file() or path.is_symlink():return None
 return hashlib.sha256(path.read_bytes()).hexdigest()
def emit(d):
 src=('state','proxy_sha256','bridge_sha256','frozen_catalog_sha256',
      'nested_owner_path_absolute','nested_owner_path_relative')
 print('NATIVE_V122_SOURCE='+json.dumps({k:d[k] for k in src},sort_keys=True,separators=(',',':')))
 print('NATIVE_V122_RUNTIME='+json.dumps({k:v for k,v in d.items() if k not in src},
       sort_keys=True,separators=(',',':')))
paths=json.loads(base64.b64decode('___ROUTES___',validate=True))
if len(paths)!=92 or len(set(paths))!=92:raise RuntimeError('HOLD_MATRIX_92')
ps=sha(proxy);bs=sha(bridge);cs=sha(catalog)
if not ps or not bs or not cs:raise RuntimeError('HOLD_NATIVE_SOURCE_MISSING')
raw=bridge.read_bytes()
def anonymous(path):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=4) as r:return r.status
 except urllib.error.HTTPError as exc:return exc.code
 except Exception:return 0
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=4) as r:return r.status
 except Exception:return 0
try:
 import chat_proxy
 api={r.path for r in chat_proxy.app.routes if isinstance(r,APIRoute)}
except Exception:raise RuntimeError('HOLD_NATIVE_ROUTE_IMPORT')
matched=sorted(set(paths)&api)
mem={'quick_check':'UNKNOWN','items':None}
try:
 import s03_memory
 db=Path(s03_memory.DB)
 if db.is_file() and not db.is_symlink():
  with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3) as con:
   con.execute('PRAGMA query_only=ON')
   mem={'quick_check':str(con.execute('PRAGMA quick_check').fetchone()[0])[:20],
        'items':int(con.execute('SELECT COUNT(*) FROM s03_items').fetchone()[0])}
except Exception:pass
gpu=[]
try:
 proc=subprocess.run(['nvidia-smi','--query-gpu=index,memory.free,utilization.gpu',
                      '--format=csv,noheader,nounits'],text=True,capture_output=True,timeout=8)
 if proc.returncode==0:
  for line in proc.stdout.splitlines()[:4]:
   parts=[x.strip() for x in line.split(',')]
   if len(parts)==3 and all(p.isdigit() for p in parts):
    gpu.append({'index':int(parts[0]),'free_mib':int(parts[1]),
                'utilization_percent':int(parts[2])})
except Exception:pass
disk={'free_bytes':None}
try:
 v=os.statvfs('/root/nox');disk['free_bytes']=v.f_bavail*v.f_frsize
except Exception:pass
emit({'state':'READ_ONLY_OBSERVED',
 'proxy_sha256':ps,'bridge_sha256':bs,'frozen_catalog_sha256':cs,
 'nested_owner_path_absolute':b'/nox-web-v29/native-owner.js' in raw,
 'nested_owner_path_relative':b'./native-owner.js' in raw,
 'stop_present':any(Path(x).exists() for x in stops),
 'health_8080':health(8080),'health_8081':health(8081),
 'anon_page':anonymous('/nox-web-v29/chat.html'),
 'anon_owner_js':anonymous('/nox-web-v29/native-owner.js'),
 'api_direct_matches':len(matched),'api_expected':len(paths),
 'api_unmapped':len(paths)-len(matched),
 's03':mem,'gpu':gpu,'disk':disk,
 'user_records_exported':False,'owner_credentials_exported':False,
 'native_service_restarted':False,'weights_touched':False})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    data=json.loads(MATRIX.read_text(encoding='utf-8'))
    paths=sorted(str(x['route']) for x in data['functions'])
    if len(paths)!=92 or len(set(paths))!=92:
        raise RuntimeError('HOLD_FROZEN_WEB_MATRIX')
    ssh.REMOTE=REMOTE_TEMPLATE.replace('___ROUTES___',
        base64.b64encode(json.dumps(paths,separators=(',',':')).encode()).decode())
    original_api=ssh.api
    def retry(method,path,key,data=None):
        for attempt in range(4):
            try:
                result=original_api(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return result
            except RuntimeError as exc:
                if method!='GET' or str(exc)!='HOLD_VAST_API_HTTP_429' or attempt==3:
                    raise
                time.sleep((10,20,40)[attempt])
    ssh.api=retry
    buffer=io.StringIO()
    okay=False
    try:
        with contextlib.redirect_stdout(buffer):okay=ssh.probe()
    except Exception as exc:
        msg=str(exc)
        print('NOX_V122_SSH_HOLD='+(msg if msg.startswith('HOLD_') and len(msg)<100 else 'TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(buffer):
                if ssh.cleanup() is not True:okay=False
        except Exception:okay=False
    lines=buffer.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V122_SOURCE=','NATIVE_V122_RUNTIME=',
                            'TEMP_SSH_CLEANUP=','SSH_ATTEMPT_','SSH_FAILURE_CLASS=',
                            'NOX_NATIVE_')) and len(line)<800:
            print(line)
    source=[line for line in lines if line.startswith('NATIVE_V122_SOURCE=')]
    runtime=[line for line in lines if line.startswith('NATIVE_V122_RUNTIME=')]
    result=bool(okay and len(source)==1 and len(runtime)==1 and
                'NATIVE_READ_ONLY_COMPLETE=true' in lines)
    print('NOX_V122_READ_ONLY_NATIVE_AUDIT='+('PASS' if result else 'HOLD'))
    return 0 if result else 2

if __name__=='__main__':
    raise SystemExit(main())
