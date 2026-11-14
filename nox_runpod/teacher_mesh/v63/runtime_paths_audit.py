"""Native read-only inspection of actual NOX interpreter environments and main model symlink.

Never runs trainer, downloads, starts services or reads model weights. Reuses
V51 temporary authenticated SSH with revocation.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time
_a=c.api
def _delay(method,path,key,data=None):
    r=_a(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,json,shutil,subprocess,configparser,shlex
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_INTERPRETERS_MODELS_V1')
model=Path('/root/nox/models/current.gguf')
try:
    resolved=model.resolve(strict=True)
    present=resolved.is_file()
    info={'name':'current.gguf','link':model.is_symlink(),'resolved_file_exists':present,
          'size_bytes':resolved.stat().st_size if present else None,
          'resolved_under_nox':resolved.is_relative_to(Path('/root/nox')),
          'target_basename':resolved.name[:100]}
except (OSError,ValueError):
    info={'name':'current.gguf','link':model.is_symlink(),'resolved_file_exists':False}
print('NATIVE_MAIN_MODEL_POINTER='+json.dumps(info,separators=(',',':')))

configs=('/etc/supervisor/conf.d/nox-t855u.conf',
 '/etc/supervisor/conf.d/nox-t802u.conf','/etc/supervisor/conf.d/nox-t811u.conf')
names=('nox-agent-tuner-t858u','nox-downloads-t802u',
       'nox-teacher-bringup','nox-teacher-serve-t811u','nox-train-worm-t811u')
candidate=set()
for config in configs:
    conf=configparser.ConfigParser(interpolation=None,strict=False)
    try:conf.read(config)
    except (OSError,configparser.Error):continue
    for name in names:
        if not conf.has_section('program:'+name):continue
        o=dict(conf.items('program:'+name))
        try:arguments=shlex.split(o.get('command',''))
        except ValueError:arguments=[]
        exe=arguments[0] if arguments else ''
        if exe.startswith('/'):
            exe_found=Path(exe).is_file()
            if exe_found and Path(exe).name.startswith('python'):
                candidate.add(exe)
        else:
            exe_found=bool(shutil.which(exe))
        data={'service':name,'exe_basename':Path(exe).name[:45],
              'exe_absolute':exe.startswith('/'),
              'exe_found_in_current_ssh_path':exe_found,
              'configured_directory_exists':Path(o['directory']).is_dir() if o.get('directory') else None}
        print('NATIVE_SERVICE_INTERPRETER='+json.dumps(data,separators=(',',':')))
known=('/usr/bin/python3','/usr/local/bin/python3','/usr/local/bin/python',
       '/root/nox/venv/bin/python','/root/nox/.venv/bin/python',
       '/root/nox_learn/venv/bin/python','/root/nox_learn/.venv/bin/python',
       '/opt/venv/bin/python','/root/miniconda3/bin/python',
       '/root/nox/agent/venv/bin/python','/root/nox/training/venv/bin/python')
for p in known:
    if Path(p).is_file():candidate.add(p)
code=('import json,importlib.metadata as md,importlib.util as iu;'
      'names=["huggingface-hub","torch","transformers","accelerate","peft","datasets","trl"];'
      'vals={};'
      '\nfor n in names:\n'
      ' try:vals[n]=md.version(n)[:24]\n'
      ' except md.PackageNotFoundError:vals[n]=None\n'
      'print(json.dumps(vals,separators=(",",":")))')
for p in sorted(candidate)[:12]:
    try:
        res=subprocess.run([p,'-I','-c',code],capture_output=True,text=True,timeout=6)
        if res.returncode==0 and len(res.stdout)<1000:
            packages=json.loads(res.stdout)
            state={'interpreter_basename':Path(p).name,
                   'path_fingerprint':__import__('hashlib').sha256(p.encode()).hexdigest()[:12],
                   'packages':packages}
        else:state={'interpreter_basename':Path(p).name,'status':'HOLD_INTERPRETER'}
    except (OSError,subprocess.TimeoutExpired,ValueError):
        state={'interpreter_basename':Path(p).name,'status':'HOLD_INTERPRETER'}
    print('NATIVE_PYTHON_ENV='+json.dumps(state,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    c.REMOTE=REMOTE;c.api=_delay
    ok=False
    try:ok=c.probe()
    except Exception as e:
        value=str(e)
        print("NOX_V63_RUNTIME="+value if value.startswith("HOLD_") and len(value)<100 else "NOX_V63_RUNTIME=HOLD_NATIVE")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print("NOX_V63_RUNTIME=HOLD_CLEANUP")
            ok=False
    return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
