"""V64: one exact native no-download patch for existing stopped NOX downloader.

Only adds verified existing NOX virtualenv's hf CLI to the downloader script PATH.
No packages downloaded, no teacher/model/trainer started, no supervisor changes.
Backup, exact SHA preimage, syntax check, postimage readback and rollback.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
import time
_base_api=ssh.api
def _safe_vast_api(method,path,key,data=None):
    result=_base_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(12)
    return result

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,hashlib,json,re,stat,shlex,shutil,subprocess,configparser,tempfile
from pathlib import Path
import fcntl
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V64_ONE_PATCH_ONE_TEST_ONE_SAVE_V1')

EXPECTED_DOWNLOADER_SHA='ed83da5dbf9692166ef2a1f26c37d4402e16f0cf0f5ce6aabae06a0884f07267'
EXPECTED_CONFIG_SHA='6f78469d6e8f41698710b947f213bfa1f4934ed2d3aabf8d728807c03899c152'
CONFIG=Path('/etc/supervisor/conf.d/nox-t802u.conf')
TUNER=Path('/etc/supervisor/conf.d/nox-t855u.conf')
TARGET='nox-downloads-t802u'
STOP_PATHS=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
            '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
def sha(blob):return hashlib.sha256(blob).hexdigest()
def emit(data):print('NATIVE_DOWNLOAD_CLI_REPAIR='+json.dumps(data,sort_keys=True,separators=(',',':')))
def hold(reason,additional=None):
    data={'state':reason,'service':TARGET,'download_started':False,
          'teacher_or_training_started':False,'supervisor_mutated':False}
    if additional:data.update(additional)
    emit(data)
    print('NATIVE_READ_ONLY_COMPLETE=true')
    raise SystemExit(0)
def supervisor_state():
    p=subprocess.run(['supervisorctl','status',TARGET],capture_output=True,text=True,timeout=10)
    words=p.stdout.strip().split()
    return words[1] if p.returncode==0 and len(words)>=2 else 'UNKNOWN'
def read_conf(p):
    c=configparser.ConfigParser(interpolation=None,strict=False)
    c.read(str(p))
    return c
if not CONFIG.is_file() or sha(CONFIG.read_bytes())!=EXPECTED_CONFIG_SHA:
    hold('HOLD_DOWNLOAD_CONFIG_SHA')
if not TUNER.is_file():
    hold('HOLD_TUNER_CONFIG_MISSING')
if any(Path(p).exists() for p in STOP_PATHS):
    hold('HOLD_GLOBAL_STOP')
if supervisor_state()!='STOPPED':
    hold('HOLD_DOWNLOADER_NOT_STOPPED')
try:free=shutil.disk_usage('/workspace').free
except OSError:hold('HOLD_DISK_UNAVAILABLE')
if free<16_000_000_000:hold('HOLD_DISK_BELOW_PATCH_FLOOR')
conf=read_conf(CONFIG)
tconf=read_conf(TUNER)
if not conf.has_section('program:'+TARGET) or not tconf.has_section('program:nox-agent-tuner-t858u'):
    hold('HOLD_SUPERVISOR_SCHEMA')
try:
    args=shlex.split(conf.get('program:'+TARGET,'command'))
    pyargs=shlex.split(tconf.get('program:nox-agent-tuner-t858u','command'))
except ValueError:hold('HOLD_CONFIG_COMMAND_PARSE')
scripts=[x for x in args[1:10] if x.endswith('.sh') and not x.startswith('-')]
if len(scripts)!=1 or not pyargs:hold('HOLD_SCRIPT_OR_PY_AMBIGUOUS')
script=Path(scripts[0])
if not script.is_absolute():
    work=conf.get('program:'+TARGET,'directory',fallback='')
    if not work:hold('HOLD_RELATIVE_SCRIPT')
    script=Path(work)/script
if script.is_symlink() or not script.is_file():hold('HOLD_SCRIPT_NOT_REGULAR')
interpreter=Path(pyargs[0])
bin_dir=interpreter.parent
hf=bin_dir/'hf'
if (not interpreter.is_absolute() or not interpreter.is_file() or
    not bin_dir.is_dir() or not hf.is_file() or not os.access(hf,os.X_OK)):
    hold('HOLD_NO_EXISTING_HF_CLI')
if not str(interpreter).startswith(('/root/nox/','/root/nox_learn/','/opt/')):
    hold('HOLD_UNTRUSTED_VENV')
if not re.fullmatch(r'[A-Za-z0-9_./-]{6,180}',str(bin_dir)):
    hold('HOLD_UNSAFE_VENV_PATH')
with script.open('rb') as f: before=f.read(200000)
if sha(before)!=EXPECTED_DOWNLOADER_SHA or len(before)>100000:
    hold('HOLD_DOWNLOADER_PREIMAGE_SHA')
if not before.startswith(b'#!') or b'\n' not in before[:300]:
    hold('HOLD_SCRIPT_SHEBANG')
# Insert PATH after existing shebang, never alter original commands or functions.
pos=before.index(b'\n')+1
marker=('# NOX-V64 verified existing hf CLI; no downloads are triggered by this patch\n'
        'export PATH="'+str(bin_dir)+':$PATH"\n').encode('utf-8')
if b'NOX-V64 verified existing hf CLI' in before:
    hold('HOLD_ALREADY_PATCHED_UNEXPECTED_SHA')
after=before[:pos]+marker+before[pos:]
if sha(before)==sha(after):hold('HOLD_NO_OP')
flags=script.stat()
if not stat.S_ISREG(flags.st_mode):hold('HOLD_SCRIPT_NOT_FILE')
backup=script.with_name(script.name+'.nox-v64-backup-'+EXPECTED_DOWNLOADER_SHA[:12])
lock=script.with_name(script.name+'.nox-v64.lock')
if any(Path(p).exists() for p in STOP_PATHS):hold('HOLD_STOP_CHANGED')
def syntax(data):
    with tempfile.NamedTemporaryFile(prefix='.nox-v64-check-',dir=script.parent,delete=False) as f:
        path=Path(f.name)
        f.write(data);f.flush();os.fsync(f.fileno())
    try:
        r=subprocess.run(['/bin/bash','-n',str(path)],capture_output=True,timeout=7)
        return r.returncode==0
    finally:path.unlink(missing_ok=True)
if not syntax(after):hold('HOLD_PATCH_SYNTAX')
# Atomic, exact-file lock guards against a concurrent patch. No supervisor restart.
with lock.open('a+b') as lk:
    fcntl.flock(lk,fcntl.LOCK_EX)
    if sha(script.read_bytes())!=EXPECTED_DOWNLOADER_SHA:hold('HOLD_CONCURRENT_CHANGE')
    if supervisor_state()!='STOPPED' or any(Path(p).exists() for p in STOP_PATHS):
        hold('HOLD_SERVICE_OR_STOP_CHANGED')
    if backup.exists():
        if not backup.is_file() or sha(backup.read_bytes())!=EXPECTED_DOWNLOADER_SHA:
            hold('HOLD_BACKUP_CONFLICT')
    else:
        fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as out:
            out.write(before);out.flush();os.fsync(out.fileno())
        os.chmod(backup,stat.S_IMODE(flags.st_mode))
        os.chown(backup,flags.st_uid,flags.st_gid)
    if sha(backup.read_bytes())!=EXPECTED_DOWNLOADER_SHA:hold('HOLD_BACKUP_VERIFY')
    tmp=None;installed=False;rolled_back=False
    try:
        fd,name=tempfile.mkstemp(prefix='.nox-v64-install-',dir=script.parent)
        tmp=Path(name)
        with os.fdopen(fd,'wb') as stream:
            stream.write(after);stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp,stat.S_IMODE(flags.st_mode))
        os.chown(tmp,flags.st_uid,flags.st_gid)
        if sha(tmp.read_bytes())!=sha(after):raise RuntimeError('HOLD_TEMP_SHA')
        os.replace(tmp,script)
        tmp=None;installed=True
        if (sha(script.read_bytes())!=sha(after) or not syntax(script.read_bytes()) or
            supervisor_state()!='STOPPED' or any(Path(p).exists() for p in STOP_PATHS)):
            raise RuntimeError('HOLD_POST_PATCH_TEST')
    except Exception:
        if tmp is not None:tmp.unlink(missing_ok=True)
        if installed and sha(script.read_bytes())==sha(after):
            try:
                restore=backup.read_bytes()
                fd,name=tempfile.mkstemp(prefix='.nox-v64-rollback-',dir=script.parent)
                with os.fdopen(fd,'wb') as fdout:
                    fdout.write(restore);fdout.flush();os.fsync(fdout.fileno())
                os.chmod(name,stat.S_IMODE(flags.st_mode))
                os.chown(name,flags.st_uid,flags.st_gid)
                os.replace(name,script)
                rolled_back=sha(script.read_bytes())==EXPECTED_DOWNLOADER_SHA
            except Exception:rolled_back=False
        hold('HOLD_PATCH_ROLLBACK',{'rolled_back_verified':rolled_back})
    emit({'state':'NATIVE_DOWNLOAD_CLI_PATH_PATCHED','service':TARGET,
          'original_sha256':EXPECTED_DOWNLOADER_SHA,
          'patched_sha256':sha(after),'backup_sha256':sha(backup.read_bytes()),
          'bash_syntax_pass':True,'hf_binary_executable':True,
          'supervisor_state':'STOPPED','disk_free_bytes':free,
          'download_started':False,'teacher_or_training_started':False,
          'supervisor_mutated':False,'source_changes_lines':2})
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

def main():
    import contextlib,io,json
    ssh.REMOTE=REMOTE
    ssh.api=_safe_vast_api
    trace=io.StringIO()
    completed=False
    revoked=False
    try:
        with contextlib.redirect_stdout(trace):
            completed=ssh.probe()
    except Exception:
        print("NOX_V64_PATCH=HOLD_NATIVE_SSH")
    finally:
        try:
            with contextlib.redirect_stdout(trace):
                revoked=ssh.cleanup()
        except Exception:
            print("NOX_V64_PATCH=HOLD_TEMP_KEY_REVOKE")
    receipts=[]
    for line in trace.getvalue().splitlines():
        if line.startswith('NATIVE_DOWNLOAD_CLI_REPAIR=') and len(line)<1200:
            try:
                r=json.loads(line.split('=',1)[1])
                if isinstance(r,dict) and r.get('service')=='nox-downloads-t802u':
                    print(line);receipts.append(r)
            except (ValueError,TypeError):pass
        elif line.startswith("TEMP_SSH_CLEANUP="):
            print(line[:120])
    accepted=(completed is True and revoked is True and len(receipts)==1 and
              receipts[0].get('state')=='NATIVE_DOWNLOAD_CLI_PATH_PATCHED' and
              receipts[0].get('bash_syntax_pass') is True)
    print("NOX_V64_CLI_PATCH_VERIFIED="+str(accepted).lower())
    if not accepted:print("NOX_V64_PATCH=HOLD_NOT_ACCEPTED")
    return 0 if accepted else 2

if __name__=="__main__":
    raise SystemExit(main())
