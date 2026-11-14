"""NOX V63: actual missing commands/imports and restart-risk evidence for five services.

The output contains only controlled error categories and hashes. No raw logs,
command arguments, credentials, files, prompt contents, or memory leave Vast.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as connection
import time

# V51 is shared with executor #2. Keep its source unchanged. Vast may accept an
# attached key before sshd can use it. Delay only THIS read-only probe's first
# SSH attempt, then V51's bounded retry and mandatory revoke still apply.
_v51_api = connection.api
def _api_with_ssh_propagation(method, path, key, data=None):
    result = _v51_api(method, path, key, data)
    if method == "POST" and path.endswith("/ssh/"):
        time.sleep(12)
    return result

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import ast,configparser,hashlib,os,re,shlex,shutil,subprocess,json
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_SERVICE_FAILURE_EVIDENCE_V1')
SERVICES=(
 'nox-agent-tuner-t858u','nox-downloads-t802u','nox-teacher-bringup',
 'nox-teacher-serve-t811u','nox-train-worm-t811u'
)
CONF=('/etc/supervisor/conf.d/nox-t855u.conf',
'/etc/supervisor/conf.d/nox-t802u.conf','/etc/supervisor/conf.d/nox-t811u.conf')
KNOWN_COMMANDS=('curl','wget','python','python3','pip','pip3','git',
 'hf','huggingface-cli','aria2c','rclone','jq','rsync','tar','unzip',
 'llama-server','flock','sha256sum','nvidia-smi','bash','sleep','openssl',
 'supervisorctl','conda','uv','accelerate')
def run(command):
    try:
        x=subprocess.run(command,capture_output=True,text=True,timeout=7)
        return x.returncode,x.stdout[-20000:]
    except (OSError,subprocess.TimeoutExpired):return -1,''
def cfg(name):
    for file in CONF:
        if not Path(file).is_file():continue
        conf=configparser.ConfigParser(interpolation=None,strict=False)
        try:conf.read(file)
        except (OSError,configparser.Error):continue
        sec='program:'+name
        if conf.has_section(sec):return dict(conf.items(sec))
    return {}
def filefromcommand(opts):
    command=opts.get('command','')
    try:p=shlex.split(command)
    except ValueError:return None
    candidates=[a for a in p[1:10] if a.lower().endswith(('.py','.sh')) and not a.startswith('-')]
    if not candidates:return None
    file=Path(candidates[0])
    if not file.is_absolute() and opts.get('directory'):file=Path(opts['directory'])/file
    return file if file.is_file() and not file.is_symlink() else None
def safe_log(name):
    for channel in ('stderr','stdout'):
        rc,blob=run(['supervisorctl','tail','-7500',name,channel])
        if rc==0 and blob:
            yield blob
        else:
            rc,blob=run(['supervisorctl','tail',name,channel])
            if rc==0 and blob:yield blob
def errors(text):
    missing_modules=re.findall(r"no module named ['\"]([a-z0-9_.]{1,60})['\"]",text,re.I)
    missing_commands=re.findall(r"(?:^|\n)(?:[^\n]{0,100}:\s*)?([A-Za-z0-9_.-]{1,60}):\s*command not found",text,re.I)
    lines=text.splitlines()
    exceptions=[]
    for line in lines[-160:]:
        found=re.match(r"^\s*([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Exit))(?::|$)",line)
        if found and found.group(1) not in exceptions:exceptions.append(found.group(1))
    if 'traceback (most recent call last)' in text.lower() and not exceptions:
        exceptions.append('UNCLASSIFIED_TRACEBACK')
    missing_exec=re.findall(r"exec: ([A-Za-z0-9_.-]{1,60}): not found",text,re.I)
    def clean(items):
        return list(dict.fromkeys(items))[:6]
    return {'missing_commands':clean(missing_commands+missing_exec),
            'missing_modules':clean(missing_modules),
            'exception_types':clean(exceptions)}
def script_features(file):
    if file is None:return {'present':False}
    try:
        if file.stat().st_size>600000:return {'present':True,'too_large':True}
        blob=file.read_bytes()
        txt=blob.decode('utf-8',errors='replace')
    except OSError:return {'present':False}
    out={'present':True,'ext':file.suffix,'sha256':hashlib.sha256(blob).hexdigest()}
    if file.suffix=='.sh':
        seen=[c for c in KNOWN_COMMANDS if re.search(r"(?<![A-Za-z0-9_.-])"+re.escape(c)+r"(?![A-Za-z0-9_.-])",txt)]
        out['referenced_tools']=seen[:18]
        out['tools_unavailable_on_path']=[c for c in seen if not shutil.which(c)]
        out['large_download_calls']=bool(re.search(r'\b(wget|curl|aria2c|huggingface-cli|hf)\b.*\b(download|https?:)',txt))
        out['trainer_invocation']=bool(re.search(r'\b(train|distill|torchrun|accelerate)\b',txt,re.I))
    elif file.suffix=='.py':
        try:tree=ast.parse(txt)
        except SyntaxError:
            out['ast_valid']=False
            return out
        out['ast_valid']=True
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                imports.extend(x.name.split('.')[0] for x in node.names)
            if isinstance(node,ast.ImportFrom) and node.module:
                imports.append(node.module.split('.')[0])
        out['imports']=list(dict.fromkeys(imports))[:25]
        out['gpu_training_related']=any(v in imports for v in ('torch','transformers','accelerate','peft','deepspeed'))
        out['writes_files_related']=bool(re.search(r'\b(write_text|write_bytes|torch\.save|open\s*\(.{0,50}["\x27]w|unlink|remove)\b',txt))
    return out
for service in SERVICES:
    opts=cfg(service)
    file=filefromcommand(opts)
    logs='\n'.join(list(safe_log(service)))[-25000:]
    detail=errors(logs)
    report={'service':service,'log_sha256':hashlib.sha256(logs.encode()).hexdigest() if logs else None,
            'log_bytes_bounded':len(logs),'errors':detail,
            'script':script_features(file),'autostart':opts.get('autostart'),
            'autorestart':opts.get('autorestart')}
    print('NATIVE_SERVICE_CAUSE='+json.dumps(report,separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main()->int:
    connection.REMOTE=REMOTE
    connection.api=_api_with_ssh_propagation
    ok=False
    try:ok=connection.probe()
    except Exception as e:
        value=str(e)
        print("NOX_V63_CAUSE="+value if value.startswith("HOLD_") and len(value)<90 else "NOX_V63_CAUSE=HOLD_NATIVE_FAILURE")
    finally:
        try:
            if not connection.cleanup():ok=False
        except Exception:
            print("NOX_V63_CAUSE=HOLD_KEY_REVOKE")
            ok=False
    return 0 if ok else 2

if __name__=="__main__":raise SystemExit(main())
