"""V122 read-only physical owner WEB preflight on existing Vast instance 60509551.

No credential/cookie or private S03 row leaves OneHost; no server code, model,
weight, checkpoint, S03 data or processes are modified. Temporary SSH revoked.
"""
from __future__ import annotations
import contextlib,io,json,time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh

REMOTE=r"""
set -euo pipefail
cd /root/nox/scripts
/root/nox/venv/bin/python - <<'PYREMOTE'
import hashlib,json,urllib.error,urllib.request
from pathlib import Path
from fastapi.routing import APIRoute
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V122_EXISTING_OWNER_WEB_READONLY_V1')
base=Path('/root/nox/scripts')
proxy=base/'chat_proxy.py'
bridge=base/'nox_v29_chat_bridge.py'
original=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-ui.js')
expected='c5f6b23d5fc6c31c4c388a574bfa8c61243cda6000cefb0026732ebe4183b765'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
def get(path):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080'+path,timeout=4) as r:return r.status
 except urllib.error.HTTPError as e:return e.code
 except Exception:return None
def health(port):
 try:
  with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=4) as r:return r.status
 except Exception:return None
stop=any(Path(p).exists() for p in ('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag','/workspace/NOX_STOP'))
status='HOLD_SOURCE_OR_HEALTH'
counts={}
try:
 import chat_proxy
 routes={r.path for r in chat_proxy.app.routes if isinstance(r,APIRoute)}
 counts={'native_api':len(routes),'ui_status':'/api/nox/status' in routes,'ui_activity':'/api/nox/activity' in routes}
except Exception:pass
checks={
 'frozen_source_sha_ok':sha(original)==expected,
 'owner_bridge_exists':sha(bridge) is not None,
 'auth_401':get('/api/nox/activity')==401 and get('/api/health')==401,
 'proxy_health_200':health(8080)==200,
 'model_health_200':health(8081)==200,
 'stop_present':stop,
}
if all(checks[k] for k in ('frozen_source_sha_ok','owner_bridge_exists','auth_401','proxy_health_200','model_health_200')) and not stop:
 status='PASS_STAGING_PREFLIGHT'
bridgecode=bridge.read_text(encoding='utf-8',errors='replace') if sha(bridge) else ''
# Read-only SHA/pinned-anchor conflict localization, without returning code or secrets.
import shutil,sqlite3
space=shutil.disk_usage('/workspace')
structural={
 'bridge_expected_sha':sha(bridge)=='cc27928b38f9b86d2375de8092d09dbdc34f81c6e51e8a68d36041ee71529750',
 'proxy_expected_sha':sha(proxy)=='4d90215d7099344dd5aaed2412645b764baa0228acc0b0e153cfe425217591ad',
 'web_expected_sha':sha(original)==expected,
 'owner_static_class_count':bridgecode.count('class _OwnerStatic(StaticFiles):'),
 'static_response_anchor_count':bridgecode.count('        response=await super().get_response(path,scope)'),
 'owner_ui_overlay_present':'def _overlay_v122_owner_ui' in bridgecode,
 'owner_js_route_present':"path.lstrip('/')=='nox-ui.js'" in bridgecode,
 'catalog_fix_present':'_catalog_owner_overlay' in bridgecode,
 'async_stop_present':'_next_native_chunk_or_stop' in bridgecode,
 'bridge_bytes':bridge.stat().st_size if bridge.is_file() else None,
 'proxy_bytes':proxy.stat().st_size if proxy.is_file() else None,
 'workspace_free_bytes':space.free,
}
try:
 import s03_memory
 db=Path(s03_memory.DB)
 with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3) as con:
  con.execute('PRAGMA query_only=ON')
  structural['s03_quick_check']=con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
except Exception:structural['s03_quick_check']=False
receipt={'state':status,'checks':checks,'registered':counts,'sha_drift_diagnosis':structural,
 'frozen_js_sha256':sha(original),'bridge_sha256':sha(bridge),'proxy_sha256':sha(proxy),
 'v122_native_overlay_present':'def _overlay_v122_owner_ui' in bridgecode,
 'private_rows_exported':False,'password_or_cookie_exported':False,
 'services_restarted':False,'model_weights_modified':False}
print('NATIVE_V122_PREFLIGHT='+json.dumps(receipt,separators=(',',':'),sort_keys=True))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    ssh.REMOTE=REMOTE
    old=ssh.api
    def api(method,path,key,data=None):
        for attempt in range(4):
            try:
                answer=old(method,path,key,data)
                if method=='POST' and path.endswith('/ssh/'):time.sleep(12)
                return answer
            except RuntimeError as ex:
                if method!='GET' or str(ex)!='HOLD_VAST_API_HTTP_429' or attempt==3:raise
                time.sleep((10,20,40)[attempt])
    ssh.api=api
    stream=io.StringIO();transport=False;cleanup=False
    try:
        with contextlib.redirect_stdout(stream):transport=ssh.probe()
    except Exception as exc:
        reason=str(exc)
        print('NOX_V122_TRANSPORT_HOLD='+(reason if reason.startswith('HOLD_') and len(reason)<90 else 'HOLD_SSH_TRANSPORT'))
    finally:
        try:
            with contextlib.redirect_stdout(stream):cleanup=ssh.cleanup()
        except Exception:cleanup=False
    lines=stream.getvalue().splitlines()
    for line in lines:
        if line.startswith(('NATIVE_V122_','NATIVE_AUDIT_SCHEMA=','TEMP_SSH_CLEANUP=')) and len(line)<1800:
            print(line)
    receipts=[x.split('=',1)[1] for x in lines if x.startswith('NATIVE_V122_PREFLIGHT=')]
    accepted=False
    if len(receipts)==1:
        try:accepted=json.loads(receipts[0]).get('state')=='PASS_STAGING_PREFLIGHT'
        except (TypeError,ValueError):pass
    good=bool(transport and cleanup and accepted and 'NATIVE_READ_ONLY_COMPLETE=true' in lines)
    print('NOX_V122_READONLY_NATIVE_PREFLIGHT_ACCEPTED='+str(good).lower())
    print('NOX_V122_LIVE_DEPLOYED=false')
    return 0 if good else 2

if __name__=='__main__':raise SystemExit(main())
