"""NOX E2: static frontend URL map and server process binding; read only."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
import time
_prior=conn.api
def delayed(method,path,key,data=None):
    x=_prior(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return x
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,subprocess,ast,json
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_E2_BACKEND_FRONTEND_ROUTE_MATCH_V1')
ports={8080,8081,8082,8084,8087,8088,8092,8093,8095,8384,8888,11111,11112}
try:
    proc=subprocess.run(['ss','-H','-ltnp'],capture_output=True,text=True,timeout=6)
    if proc.returncode==0:
        for line in proc.stdout.splitlines()[:160]:
            found=re.search(r':([0-9]{2,5})\s',line)
            if not found or int(found.group(1)) not in ports:continue
            port=int(found.group(1))
            foundpid=re.search(r'pid=([0-9]+)',line)
            if not foundpid:
                print('NATIVE_ROUTE_PORT_'+str(port)+'=PID_UNAVAILABLE');continue
            pid=foundpid.group(1)
            try:
                comm=(Path('/proc')/pid/'comm').read_text().strip()
                cmd=(Path('/proc')/pid/'cmdline').read_bytes()[:3000].split(b'\0')
                scripts=[]
                for token in cmd:
                    if not token or b'=' in token or len(token)>240:continue
                    name=os.path.basename(token.decode(errors='replace'))
                    if re.fullmatch('[A-Za-z0-9_.-]{1,75}',name) and name.endswith(('.py','.sh')):
                        scripts.append(name)
                print('NATIVE_ROUTE_PORT_'+str(port)+'='+pid+':'+re.sub('[^A-Za-z0-9_.-]','',comm[:30])+':'+','.join(scripts[:3]))
            except OSError: print('NATIVE_ROUTE_PORT_'+str(port)+'=PROCESS_GONE')
except (OSError,subprocess.TimeoutExpired):
    print('NATIVE_ROUTE_BINDINGS=HOLD')
js=Path('/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-chat.js')
if js.is_file() and js.stat().st_size<1_000_000:
    txt=js.read_text(encoding='utf-8',errors='replace')
    urls=set()
    for regex in (r"""fetch\(\s*['"](/[-_a-zA-Z0-9/{}/.]{1,110})""",
                  r"""['"](/(?:api|v1|nox|chat|resonance)[/_a-zA-Z0-9/{}/.]{1,110})['"]"""):
        for match in re.findall(regex,txt):
            if len(match)<=120 and not any(x in match.lower() for x in ('token','key','secret','password')):
                urls.add(match)
    print('NATIVE_WEB_DIRECT_ROUTE_COUNT='+str(len(urls)))
    print('NATIVE_WEB_DIRECT_ROUTES='+json.dumps(sorted(urls)[:22],separators=(',',':')))
    print('NATIVE_WEB_FETCH_STREAM_READER='+str('getReader(' in txt))
    print('NATIVE_WEB_STREAM_DECODER='+str('TextDecoder' in txt))
else:print('NATIVE_WEB_SOURCE=HOLD')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    conn.REMOTE=REMOTE;conn.api=delayed;good=False
    try:good=conn.probe()
    except Exception as e:
        s=str(e);print('NOX_E2_ROUTE_MAP='+s if s.startswith('HOLD_') and len(s)<100 else 'NOX_E2_ROUTE_MAP=HOLD')
    finally:
        try:
            if not conn.cleanup():good=False
        except Exception:good=False
    raise SystemExit(0 if good else 2)
