"""Read-only public NOX web entrypoint discovery on the existing Vast instance.

Inspects authenticated Vast metadata and local HTTP health. Does NOT publish
private/unauthenticated services, install routes, or modify processes.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import json
import os
import urllib.request
import urllib.error
import ipaddress
import time

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,urllib.request,urllib.error,subprocess
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V70_WEB_ENTRYPOINT_DISCOVERY_V1')
for port in (80,443,8080,8081,8384,8888,11555,18775,18877):
    for path in ('/', '/health', '/api/nox/status'):
        try:
            with urllib.request.urlopen(urllib.request.Request(
              f'http://127.0.0.1:{port}{path}',headers={'User-Agent':'NOX-native-health-readonly'}),
              timeout=2.0) as r:
                code=r.status
                ct=r.headers.get('Content-Type','')[:70]
        except urllib.error.HTTPError as e:
            code=e.code; ct=''
        except Exception:
            code=0; ct=''
        if code:
            print('NATIVE_WEB_LOCAL='+json.dumps({'port':port,'path':path,'http':code,
                  'content_type':ct},separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    key=os.environ.get('NOX2','')
    if not key:raise SystemExit('HOLD_NOX2')
    try:
        d=ssh.api('GET',f'/instances/{ssh.INSTANCE}/',key)
        d=d.get('instances',d) if isinstance(d,dict) else {}
        if isinstance(d,list):d=next((x for x in d if str(x.get('id'))==str(ssh.INSTANCE)),{})
        if not isinstance(d,dict):raise RuntimeError('HOLD_METADATA')
        public_ip=d.get('public_ipaddr')
        if not ipaddress.ip_address(public_ip).is_global:raise RuntimeError('HOLD_PUBLIC_IP')
        ports=d.get('ports') or {}
        print('NOX_INSTANCE_STATUS='+str(d.get('actual_status')))
        print('NOX_PUBLIC_IP='+public_ip)
        print('NOX_INSTANCE_PORTS='+json.dumps({k:[str(vv.get('HostPort')) for vv in v if isinstance(vv,dict)] if isinstance(v,list) else []
            for k,v in ports.items() if str(k).split('/')[0] in ('80','443','8080','8384','8888','11555','18775','18877')},separators=(',',':')))
        ssh.REMOTE=REMOTE
        ok=False
        try:ok=ssh.probe()
        finally:
            if not ssh.cleanup():ok=False
        return 0 if ok else 2
    except Exception as e:
        s=str(e)
        print('NOX_WEB_DISCOVERY='+s if s.startswith('HOLD_') and len(s)<90 else 'NOX_WEB_DISCOVERY=HOLD')
        try:ssh.cleanup()
        except Exception:pass
        return 2

if __name__=='__main__':
    raise SystemExit(main())
