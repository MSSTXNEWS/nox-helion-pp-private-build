"""Read-only shell function source/lineage audit of installed NOX scripts.

Detect missing helper definitions and syntax errors without executing scripts.
Uses the proven V51 temporary SSH route; no new backend or scheduler.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
import time

_old_api=connection.api
def _api_delayed(method,path,key,data=None):
    response=_old_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return response

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,re,shlex,configparser,hashlib,subprocess,json
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_SHELL_FUNCTION_AUDIT_V1')
GROUPS=(
 ('nox-downloads-t802u','/etc/supervisor/conf.d/nox-t802u.conf','disk_complete_for'),
 ('nox-teacher-serve-t811u','/etc/supervisor/conf.d/nox-t811u.conf','write_status'),
 ('nox-teacher-bringup','/etc/supervisor/conf.d/nox-t802u.conf',''),
)
for name,cfg,target in GROUPS:
    p=Path(cfg)
    parser=configparser.ConfigParser(interpolation=None,strict=False)
    parser.read(str(p))
    section='program:'+name
    if not parser.has_section(section):
        print('NATIVE_SCRIPT_AUDIT='+json.dumps({'service':name,'hold':'NO_PROGRAM_CONFIG'}))
        continue
    opt=dict(parser.items(section))
    command=opt.get('command','')
    try:parts=shlex.split(command)
    except ValueError:parts=[]
    candidates=[x for x in parts[1:12] if x.lower().endswith('.sh') and not x.startswith('-')]
    file=Path(candidates[0]) if candidates else None
    if file and not file.is_absolute() and opt.get('directory'):file=Path(opt['directory'])/file
    if file is None or not file.is_file():
        print('NATIVE_SCRIPT_AUDIT='+json.dumps({'service':name,'hold':'SCRIPT_ABSENT'}))
        continue
    blob=file.read_bytes()
    content=blob.decode('utf-8',errors='replace')
    lines=content.splitlines()
    defs=[];calls=[];sourcelines=[]
    for i,line in enumerate(lines,1):
        stripped=line.strip()
        if not stripped or stripped.startswith('#'):continue
        if target and re.search(r'\b'+re.escape(target)+r'\b',line):
            if re.search(r'(?:^|\s)(?:function\s+)?'+re.escape(target)+r'\s*(?:\(\s*\))?\s*\{',line):
                defs.append(i)
            else:calls.append(i)
        if re.match(r'^(source|\.)\s+',stripped):
            sourcelines.append(i)
    try:
        p=subprocess.run(['bash','-n',str(file)],capture_output=True,timeout=8)
        syntax_ok=p.returncode==0
    except (OSError,subprocess.TimeoutExpired):syntax_ok=False
    flags={
     'references_hf':bool(re.search(r'\bhf\b',content)),
     'references_wget':bool(re.search(r'\bwget\b',content)),
     'downloads_weights':bool(re.search(r'\b(hf\s+download|huggingface-cli\s+download|aria2c|wget|curl)\b',content)),
     'writes_disk':bool(re.search(r'\b(tee|>>|mv|cp|touch|mkdir|tar|unzip|rsync)\b',content)),
     'uses_supervisorctl':bool(re.search(r'\bsupervisorctl\b',content)),
     'uses_training':bool(re.search(r'\b(torchrun|accelerate|trainer|train_worm)\b',content)),
    }
    report={'service':name,'script_basename':file.name,
            'script_sha256':hashlib.sha256(blob).hexdigest(),
            'lines':len(lines),'bash_syntax_ok':syntax_ok,
            'helper_name':target or None,'definitions':defs[:15],
            'mentions_other_than_definition':calls[:20],
            'source_statement_count':len(sourcelines),
            'flags':flags}
    print('NATIVE_SCRIPT_AUDIT='+json.dumps(report,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    connection.REMOTE=REMOTE
    connection.api=_api_delayed
    ok=False
    try:ok=connection.probe()
    except Exception as e:
        val=str(e)
        print("NOX_V63_SHELL="+val if val.startswith("HOLD_") and len(val)<90 else "NOX_V63_SHELL=HOLD_NATIVE_ERROR")
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:
            print("NOX_V63_SHELL=HOLD_KEY_CLEANUP")
            ok=False
    return 0 if ok else 2

if __name__=="__main__":raise SystemExit(main())
