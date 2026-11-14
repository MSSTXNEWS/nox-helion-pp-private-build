"""NOX V73 ONEPASS: chat-first CPU scheduling for EXISTING NOX background services.

No new LLM, chat, system service, queue, scheduler, model change, S03 write or
optimizer step. Only de-prioritize an exact existing Supervisor worker after
PID/script identity and main-chat health gates. Native source readback mandatory.
"""
from __future__ import annotations
import contextlib
import io
import json
import time
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn

_api=conn.api
def _settle(method,path,key,data=None):
    v=_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):
        time.sleep(18)
    return v

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json,os,re,shutil,subprocess,time,urllib.request,urllib.error
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V73_CHAT_P0_BACKGROUND_NICE_V1')
STOP=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
      '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
targets=(('nox-agent-tuner-t858u','nox_agent_tuner_t858u.py',7),
         ('nox-teacher-serve-t811u','teacher_serve_t811u.sh',4))
def health(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as reply:
            return reply.status
    except urllib.error.HTTPError as e:return e.code
    except (OSError,urllib.error.URLError):return None
def snapshot():
    try:
        x=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.used,memory.free,utilization.gpu,temperature.gpu',
                 '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=12)
        if x.returncode!=0:return []
        rows=[]
        for line in x.stdout.splitlines()[:2]:
            v=[t.strip() for t in line.split(',')]
            if len(v)==6 and v[0].isdigit() and all(p.isdigit() for p in v[2:]):
                rows.append({'gpu':int(v[0]),'name':v[1][:36],'vram_used_mb':int(v[2]),
                'vram_free_mb':int(v[3]),'util_pct':int(v[4]),'temp_c':int(v[5])})
        return rows
    except (OSError,subprocess.TimeoutExpired):return []
def service(name):
    try:
        x=subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=10)
        if x.returncode!=0:return 'UNKNOWN',None
        words=x.stdout.strip().split()
        if len(words)<4 or words[0]!=name or words[1]!='RUNNING' or words[2]!='pid':
            return words[1] if len(words)>1 else 'UNKNOWN',None
        value=words[3].rstrip(',')
        return 'RUNNING',int(value) if value.isdigit() else None
    except (OSError,subprocess.TimeoutExpired,ValueError):return 'UNKNOWN',None
def proc_identity(pid,expected):
    if not isinstance(pid,int) or pid<2:return None
    base=Path('/proc')/str(pid)
    try:
        raw=(base/'cmdline').read_bytes().replace(b'\0',b' ').decode('utf-8','replace')
        # Only the explicitly pinned script is admitted. No raw cmdline exported.
        if expected not in raw:return None
        text=(base/'stat').read_text(errors='replace')
        tail=text.rsplit(')',1)[-1].strip().split()
        start_ticks=int(tail[19])
        nice=os.getpriority(os.PRIO_PROCESS,pid)
        return {'start_ticks':start_ticks,'nice':nice}
    except (OSError,ValueError,IndexError):return None
main=Path('/root/nox/models/current.gguf')
memory=Path('/root/nox/memory/infinite/nox_infinite_memory.sqlite3')
try:
    model=main.resolve(strict=True)
    model_verified=main.is_symlink() and model.is_file() and model.name=='nox36-mix_final_pref-Q4_K_M.gguf'
    s03_verified=memory.is_file() and memory.stat().st_size>500000
except OSError:model_verified=False;s03_verified=False
before={'chat_http':health(8080),'model_http':health(8081),
        'main_model_verified':model_verified,'s03_file_verified':s03_verified,
        'stop_active':any(Path(p).exists() for p in STOP),
        'gpus':snapshot()}
print('NATIVE_PRIME_BEFORE='+json.dumps(before,separators=(',',':')))
if before['stop_active'] or before['chat_http']!=200 or before['model_http']!=200:
    print('NATIVE_PRIME_RESULT='+json.dumps({'state':'HOLD_STOP_OR_CHAT_HEALTH',
      'background_priority_changed':False,'main_model_changed':False,
      'weights_changed':False,'training_started':False},separators=(',',':')))
    raise SystemExit(0)
if not model_verified or not s03_verified:
    print('NATIVE_PRIME_RESULT='+json.dumps({'state':'HOLD_MAIN_MODEL_OR_S03',
      'background_priority_changed':False,'main_model_changed':False,
      'weights_changed':False,'training_started':False},separators=(',',':')))
    raise SystemExit(0)
receipts=[]
changed=[]
for name,script,target_nice in targets:
    state,pid=service(name)
    data={'service':name,'supervisor_state':state,'pid':pid,'performed':False}
    first=proc_identity(pid,script) if state=='RUNNING' else None
    if not first:
        data['state']='HOLD_NOT_MATCHING_NATIVE_PROCESS'
        receipts.append(data);continue
    old=first['nice']
    data['nice_before']=old
    desired=max(old,target_nice)
    if desired>old:
        try:os.setpriority(os.PRIO_PROCESS,pid,desired)
        except (OSError,PermissionError):
            data['state']='HOLD_PRIORITY_PERMISSION'
            receipts.append(data);continue
    second=proc_identity(pid,script)
    end_state,end_pid=service(name)
    if (not second or second['start_ticks']!=first['start_ticks'] or
        second['nice']!=desired or end_state!='RUNNING' or end_pid!=pid):
        data['state']='HOLD_PID_RACE_OR_READBACK'
        receipts.append(data);continue
    data.update({'state':'BACKGROUND_CPU_PRIORITY_CONFIRMED','nice_after':second['nice'],
                 'performed':desired>old,'same_supervisor_pid':True,
                 'cpu_priority_for_chat_higher_than_background':desired>0})
    receipts.append(data)
    if desired>old:changed.append((pid,script,first['start_ticks'],old))
    print('NATIVE_PRIME_SERVICE='+json.dumps(data,separators=(',',':')))
# Check main chat again; if unhealthy, try to revert only our exact touched PIDs.
after={'chat_http':health(8080),'model_http':health(8081),
       'gpus':snapshot(),
       'disk_free_bytes':shutil.disk_usage('/workspace').free}
healthy=after['chat_http']==200 and after['model_http']==200
rollbacks=[]
if not healthy:
    for pid,script,start,old in changed:
        now=proc_identity(pid,script)
        if not now or now['start_ticks']!=start:
            rollbacks.append(False);continue
        try:
            os.setpriority(os.PRIO_PROCESS,pid,old)
            rollbacks.append(proc_identity(pid,script)['nice']==old)
        except (OSError,ValueError,TypeError):
            rollbacks.append(False)
    state='HOLD_MAIN_HEALTH_AFTER_TUNE'
else:
    state='NATIVE_CHAT_CPU_PRIORITY_APPLIED' if any(x.get('performed') for x in receipts) else (
        'ALREADY_CHAT_FIRST_NO_CPU_CHANGE' if any(x.get('state')=='BACKGROUND_CPU_PRIORITY_CONFIRMED' for x in receipts) else 'HOLD_NO_BACKGROUND_NATIVE_PROCESS')
print('NATIVE_PRIME_AFTER='+json.dumps(after,separators=(',',':')))
print('NATIVE_PRIME_RESULT='+json.dumps({
 'state':state,'changed_service_count':sum(x.get('performed') is True for x in receipts),
 'verified_service_count':sum(x.get('state')=='BACKGROUND_CPU_PRIORITY_CONFIRMED' for x in receipts),
 'service_states':[x.get('state') for x in receipts],
 'main_model_changed':False,'s03_changed':False,
 'weights_changed':False,'optimizer_steps':0,'training_started':False,
 'gpu_settings_changed':False,'service_restart_count':0,
 'rollback_success':all(rollbacks) if rollbacks else None,
 'chat_priority':'P0','background_priority':'P1'},separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main()->int:
    conn.REMOTE=REMOTE
    conn.api=_settle
    transcript=io.StringIO()
    ok=False
    cleaned=False
    try:
        with contextlib.redirect_stdout(transcript):
            ok=conn.probe()
    except Exception as err:
        txt=str(err)
        print("NOX_V73_HOLD="+txt if txt.startswith('HOLD_') and len(txt)<90 else "NOX_V73_HOLD=REMOTE_EXCEPTION")
    finally:
        try:
            with contextlib.redirect_stdout(transcript):
                cleaned=conn.cleanup()
        except Exception:
            print('NOX_V73_HOLD=TEMPORARY_KEY_REVOCATION')
    results=[]
    before=None
    after=None
    for line in transcript.getvalue().splitlines():
        if len(line)>3000:continue
        if line.startswith(('NATIVE_PRIME_RESULT=','NATIVE_PRIME_BEFORE=','NATIVE_PRIME_AFTER=','NATIVE_PRIME_SERVICE=')):
            print(line)
            try:
                key,raw=line.split('=',1)
                data=json.loads(raw)
                if key=='NATIVE_PRIME_RESULT':results.append(data)
                elif key=='NATIVE_PRIME_BEFORE':before=data
                elif key=='NATIVE_PRIME_AFTER':after=data
            except (ValueError,TypeError):pass
        if line.startswith('TEMP_SSH_CLEANUP=') and len(line)<110:print(line)
    accepted=bool(
        ok and cleaned and before and after and len(results)==1 and
        results[0].get('state') in ('NATIVE_CHAT_CPU_PRIORITY_APPLIED','ALREADY_CHAT_FIRST_NO_CPU_CHANGE') and
        results[0].get('verified_service_count',0)>0 and
        after.get('chat_http')==200 and after.get('model_http')==200
    )
    print("NOX_V73_CHAT_PRIORITY_NATIVE_VERIFIED="+str(accepted).lower())
    print("NOX_V73_WEIGHT_TRAINING_STARTED=false")
    if not accepted:print("NOX_V73_HOLD=NATIVE_PRIORITY_OR_HEALTH_NOT_VERIFIED")
    return 0 if accepted else 2

if __name__=='__main__':
    raise SystemExit(main())
