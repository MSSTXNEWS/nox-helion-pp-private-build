"""Redacted static audit of existing NOX agent control flow and process ownership."""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,re,subprocess,json,hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
path=Path('/root/nox/scripts/agent_loop.py')
if not path.is_file():raise SystemExit('HOLD_NO_SOURCE')
s=path.read_text(encoding='utf-8',errors='replace')
print('NATIVE_SOURCE_SHA256='+hashlib.sha256(s.encode()).hexdigest())
root=ast.parse(s)
for fn in ast.walk(root):
    if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)) or fn.name not in ('run_tool_loop','stream_tokens','owner_completion','prepare_payload'):
        continue
    for n in ast.walk(fn):
        if isinstance(n,ast.Yield) and isinstance(n.value,ast.Tuple) and n.value.elts:
            k=n.value.elts[0]
            if isinstance(k,ast.Constant) and isinstance(k.value,str) and len(k.value)<40 and re.fullmatch('[A-Za-z0-9_ -]+',k.value):
                print('NATIVE_YIELD_'+fn.name.upper()+'_'+str(n.lineno)+'='+k.value.replace(' ','_'))
        if isinstance(n,ast.Assign):
            for key in n.targets:
                if isinstance(key,ast.Name) and key.id in ('MAX_STEPS','MAX_TOKENS','MAX_TOOL_STEPS'):
                    if isinstance(n.value,ast.Constant) and type(n.value.value) in (int,float):
                        print('NATIVE_ASSIGN_'+key.id+'='+str(n.value.value))
for n in root.body:
    if isinstance(n,ast.Assign):
        for tar in n.targets:
            if isinstance(tar,ast.Name) and tar.id in ('MAX_STEPS','MAX_TOKENS','MAX_TOOL_STEPS'):
                if isinstance(n.value,ast.Constant) and type(n.value.value) in (int,float):
                    print('NATIVE_GLOBAL_'+tar.id+'='+str(n.value.value))
try:
    ps=subprocess.run(['ps','-eo','pid=,ppid=,comm='],capture_output=True,text=True,timeout=5)
    if ps.returncode==0:
        for line in ps.stdout.splitlines()[:400]:
            arr=line.split()
            if len(arr)<3:continue
            pid,ppid,cmd=arr[:3]
            if not pid.isdigit():continue
            if cmd.lower() not in ('python','python3','uvicorn','gunicorn'):continue
            f=Path('/proc')/pid/'cmdline'
            try:b=f.read_bytes().decode('utf-8','replace').split('\0')
            except OSError:continue
            if any('agent_loop' in a for a in b):
                print('NATIVE_AGENT_PID='+pid)
                print('NATIVE_AGENT_PPID='+ppid)
                print('NATIVE_AGENT_EXE='+cmd)
                print('NATIVE_AGENT_CMD_ARGS='+str(len(b)))
except (OSError,subprocess.TimeoutExpired):pass
for fn in ('/etc/supervisor/conf.d','/etc/supervisord.d'):
    folder=Path(fn)
    if not folder.is_dir():continue
    for conf in sorted(folder.glob('*'))[:100]:
        if conf.suffix not in ('.ini','.conf'):continue
        try:text=conf.read_text(encoding='utf-8',errors='replace')[:40000]
        except OSError:continue
        if re.search('agent_loop\\.py|agent.loop|nox-agent',text,re.I):
            if re.fullmatch('[A-Za-z0-9_.@:-]{1,100}',conf.name):
                print('NATIVE_AGENT_SUPERVISOR_CONF='+conf.name)
try:
    import configparser
    target=Path('/etc/supervisor/conf.d/nox-t855u.conf')
    if target.is_file():
        parser=configparser.ConfigParser(interpolation=None)
        parser.read(str(target),encoding='utf-8')
        for name in parser.sections():
            if not name.startswith('program:'):continue
            service=name.split(':',1)[1]
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,70}',service):continue
            cmd=parser[name].get('command','')
            print('NATIVE_SUPERVISOR_PROGRAM='+service)
            print('NATIVE_SUPERVISOR_AGENT_LOOP_COMMAND='+str('agent_loop' in cmd))
            print('NATIVE_SUPERVISOR_UVICORN_COMMAND='+str('uvicorn' in cmd))
            print('NATIVE_SUPERVISOR_AUTORESTART='+str(parser[name].get('autorestart','unknown')))
            result=subprocess.run(['supervisorctl','status',service],capture_output=True,text=True,timeout=6)
            state=(result.stdout.strip().split() or ['','HOLD'])[1] if result.returncode==0 else 'HOLD_STATUS'
            print('NATIVE_SUPERVISOR_CURRENT_STATUS='+state[:30])
except Exception as e:
    print('NATIVE_SUPERVISOR_AUDIT=HOLD_'+type(e).__name__)
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE
    valid=False
    try:valid=c.probe()
    except Exception as err:
        e=str(err)
        print('NATIVE_CONTROL_FLOW='+e if e.startswith('HOLD_') else 'NATIVE_CONTROL_FLOW=HOLD')
    finally:
        try:
            if not c.cleanup():valid=False
        except Exception:valid=False
    raise SystemExit(0 if valid else 2)
