"""Read-only: reconcile system hf not on PATH with installed NOX venv Hugging Face Hub."""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time
_a=c.api
def _delay(method,path,key,data=None):
    r=_a(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,configparser,shlex,shutil,json,re,hashlib
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_HF_CLI_ALIGNMENT_V1')
parser=configparser.ConfigParser(interpolation=None,strict=False)
for config in ('/etc/supervisor/conf.d/nox-t855u.conf','/etc/supervisor/conf.d/nox-t802u.conf','/etc/supervisor/conf.d/nox-t811u.conf'):
    try:parser.read(config)
    except (OSError,configparser.Error):pass
paths=[]
for service in ('nox-agent-tuner-t858u','nox-train-worm-t811u'):
    name='program:'+service
    if not parser.has_section(name):continue
    text=parser.get(name,'command',fallback='')
    try:args=shlex.split(text)
    except ValueError:args=[]
    if args and Path(args[0]).is_file() and Path(args[0]).name.startswith('python'):
        paths.append((service,Path(args[0])))
shell=parser.get('program:nox-downloads-t802u','command',fallback='')
try:
    argv=shlex.split(shell)
except ValueError:argv=[]
scripts=[x for x in argv[1:12] if x.endswith('.sh') and not x.startswith('-')]
p=Path(scripts[0]) if scripts else None
if p and not p.is_absolute():
    d=parser.get('program:nox-downloads-t802u','directory',fallback='')
    if d:p=Path(d)/p
src=p.read_text(errors='replace') if p and p.is_file() else ''
lines=src.splitlines()
first_hf=next((i for i,row in enumerate(lines,1) if re.search(r'(^|\s)hf\s+(download|repo)',row)),None)
first_download=next((i for i,row in enumerate(lines,1) if re.search(r'(^|\s)(hf\s+download|aria2c|curl\s+.*https?://|wget\s+)',row)),None)
gate_lines=[i for i,row in enumerate(lines,1) if re.search(r'disk_complete_for|df\s+|disk_free|reserve|free_bytes',row)]
declared_path=any('PATH=' in row or 'PATH:' in row for row in lines)
print('NATIVE_DOWNLOAD_SCRIPT_POLICY='+json.dumps({
   'script_present':bool(src),'script_sha256':hashlib.sha256(src.encode()).hexdigest() if src else None,
   'first_hf_download_line':first_hf,'first_download_line':first_download,
   'disk_gate_lines':gate_lines[:12],'declares_path':declared_path,
   'supervisor_autostart':parser.get('program:nox-downloads-t802u','autostart',fallback=None),
   'supervisor_autorestart':parser.get('program:nox-downloads-t802u','autorestart',fallback=None),
 },separators=(',',':')))
seen=set()
for service,exe in paths:
    root=exe.parent
    if str(root) in seen:continue
    seen.add(str(root))
    candidates=[root/'hf',root/'huggingface-cli']
    entry=[{'name':f.name,'present':f.is_file(),'executable':os.access(f,os.X_OK)}
           for f in candidates]
    print('NATIVE_HF_VENV_ENTRYPOINT='+json.dumps({
      'python_sha_hint':hashlib.sha256(str(exe).encode()).hexdigest()[:12],
      'interpreter_basename':exe.name,'entrypoints':entry,
      'local_hf_import_available':'NOT_TESTED'
    },separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
    c.REMOTE=REMOTE;c.api=_delay
    ok=False
    try:ok=c.probe()
    except Exception as e:
        s=str(e)
        print("NOX_V63_HF="+s if s.startswith("HOLD_") and len(s)<80 else "NOX_V63_HF=HOLD_NATIVE")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print("NOX_V63_HF=HOLD_SSH_CLEANUP")
            ok=False
    return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
