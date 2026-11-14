"""NOX V63: atomic, SHA-locked PATH fix for existing Downloads service.

Does NOT launch downloads, models or training. One tiny addition to the
existing script, independently retained original backup, bash syntax check,
native readback and no side effects on other Supervisor services.
"""
from __future__ import annotations
from .native_once import native_once
import json

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib,os,shlex,configparser,subprocess,json,shutil,tempfile,stat
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V63_HF_PATH_PATCH_V1')
NAME='nox-downloads-t802u'
EXPECTED_SHA='ed83da5dbf9692166ef2a1f26c37d4402e16f0cf0f5ce6aabae06a0884f07267'
CFG=Path('/etc/supervisor/conf.d/nox-t802u.conf')
CONFIG_SHA='6f78469d6e8f41698710b947f213bfa1f4934ed2d3aabf8d728807c03899c152'
BINS=(
 '/root/.local/bin/hf','/usr/local/bin/hf','/root/nox/.venv/bin/hf',
 '/root/nox/venv/bin/hf','/root/nox/env/bin/hf','/opt/venv/bin/hf'
)
STOP_FILES=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
 '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
MARK='# NOX_V63_HF_PATH_PIN'
def emit(state,**kwargs):
    print('NATIVE_DOWNLOAD_PATH_REPAIR='+json.dumps(dict(state=state,service=NAME,**kwargs),sort_keys=True,separators=(',',':')))
    print('NATIVE_PATCH_COMPLETE=true')
def hold(reason):
    emit(reason,patch_applied=False,download_started=False)
    raise SystemExit(0)
def status():
    p=subprocess.run(['supervisorctl','status',NAME],capture_output=True,text=True,timeout=9)
    col=p.stdout.strip().split()
    return col[1] if len(col)>1 else 'UNKNOWN'
if any(Path(p).exists() for p in STOP_FILES):hold('HOLD_STOP_ACTIVE')
if not CFG.is_file() or CFG.is_symlink() or hashlib.sha256(CFG.read_bytes()).hexdigest()!=CONFIG_SHA:
    hold('HOLD_CONFIG_SOURCE_CHANGED')
cfg=configparser.ConfigParser(interpolation=None,strict=False)
cfg.read(str(CFG))
if not cfg.has_section('program:'+NAME):hold('HOLD_PROGRAM_CONFIG_MISSING')
opt=dict(cfg.items('program:'+NAME))
try:parts=shlex.split(opt.get('command',''))
except ValueError:hold('HOLD_BAD_SUPERVISOR_COMMAND')
scripts=[x for x in parts[1:10] if x.endswith('.sh') and not x.startswith('-')]
if len(scripts)!=1:hold('HOLD_AMBIGUOUS_SCRIPT')
file=Path(scripts[0])
if not file.is_absolute() and opt.get('directory'):file=Path(opt['directory'])/file
if not file.is_file() or file.is_symlink() or file.stat().st_size>900000:hold('HOLD_SCRIPT_INVALID')
orig=file.read_bytes()
sha=hashlib.sha256(orig).hexdigest()
if MARK.encode() in orig:
    emit('ALREADY_PATCHED',patch_applied=False,download_started=False,sha256=sha)
    raise SystemExit(0)
if sha!=EXPECTED_SHA:hold('HOLD_SCRIPT_SHA_CHANGED')
before=status()
if before!='STOPPED':hold('HOLD_DOWNLOAD_SERVICE_NOT_STOPPED')
try:free=shutil.disk_usage('/workspace').free
except OSError:hold('HOLD_DISK_UNAVAILABLE')
if free<16_000_000_000:hold('HOLD_DISK_FLOOR')
candidates=[Path(p) for p in BINS if Path(p).is_file()]
if len(candidates)!=1:hold('HOLD_HF_CLI_AMBIGUOUS_OR_ABSENT')
cli=candidates[0]
if not os.access(cli,os.X_OK):hold('HOLD_HF_CLI_NOT_EXECUTABLE')
try:
    probe=subprocess.run([str(cli),'--help'],capture_output=True,timeout=8)
except (OSError,subprocess.TimeoutExpired):hold('HOLD_HF_CLI_NOT_HEALTHY')
if probe.returncode!=0:hold('HOLD_HF_CLI_NOT_HEALTHY')
# No package installation; reuse the already functioning trusted CLI in this container.
bin_path=str(cli.parent)
if bin_path not in tuple(str(Path(x).parent) for x in BINS):hold('HOLD_UNTRUSTED_CLI_PATH')
backup_dir=Path('/root/nox/backup/v63_service_repairs')
backup_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
backup=backup_dir/(file.name+'.'+EXPECTED_SHA+'.backup')
if backup.exists():
    if backup.is_symlink() or hashlib.sha256(backup.read_bytes()).hexdigest()!=EXPECTED_SHA:
        hold('HOLD_BACKUP_COLLISION')
else:
    with backup.open('xb') as fp:
        fp.write(orig)
        fp.flush()
        os.fsync(fp.fileno())
    backup.chmod(0o600)
if hashlib.sha256(backup.read_bytes()).hexdigest()!=EXPECTED_SHA:
    hold('HOLD_BACKUP_SHA_MISMATCH')
# Insert one line after shebang, leave all original bytes in the same order.
new_line=(MARK+'\nexport PATH="'+bin_path+':$PATH"\n').encode()
pos=orig.find(b'\n')+1 if orig.startswith(b'#!') and b'\n' in orig else 0
changed=orig[:pos]+new_line+orig[pos:]
if changed[:pos]+changed[pos+len(new_line):]!=orig:hold('HOLD_UNEXPECTED_DIFF')
if any(Path(p).exists() for p in STOP_FILES) or status()!='STOPPED':
    hold('HOLD_CONCURRENT_STATE_CHANGE')
tmp=None;promoted=False;rolled_back=False
try:
    fd,name=tempfile.mkstemp(prefix='.nox-v63-hf-',dir=str(file.parent))
    tmp=Path(name)
    with os.fdopen(fd,'wb') as fp:
        fp.write(changed)
        fp.flush();os.fsync(fp.fileno())
    os.chmod(tmp,stat.S_IMODE(file.stat().st_mode))
    if subprocess.run(['bash','-n',str(tmp)],capture_output=True,timeout=8).returncode!=0:
        hold('HOLD_PATCH_SYNTAX')
    os.replace(tmp,file)
    tmp=None;promoted=True
    checked=file.read_bytes()
    if checked!=changed or status()!='STOPPED' or not backup.is_file():
        raise RuntimeError('PATCH_READBACK')
    if subprocess.run(['bash','-n',str(file)],capture_output=True,timeout=8).returncode!=0:
        raise RuntimeError('PATCH_BASH_SYNTAX')
    if hashlib.sha256(backup.read_bytes()).hexdigest()!=EXPECTED_SHA:
        raise RuntimeError('BACKUP_SHA')
    emit('NATIVE_HF_PATH_PATCH_VERIFIED',patch_applied=True,download_started=False,
         original_sha256=EXPECTED_SHA,patched_sha256=hashlib.sha256(checked).hexdigest(),
         backup_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),
         stop_check_passed=True,supervisor_still_stopped=True)
except Exception:
    if promoted:
        try:
            # Atomic restoration of exact original preimage. Never touch other scripts.
            fd,name=tempfile.mkstemp(prefix='.nox-v63-rollback-',dir=str(file.parent))
            with os.fdopen(fd,'wb') as fp:
                fp.write(orig);fp.flush();os.fsync(fp.fileno())
            os.chmod(name,stat.S_IMODE(file.stat().st_mode))
            os.replace(name,file)
            rolled_back=hashlib.sha256(file.read_bytes()).hexdigest()==EXPECTED_SHA
        except Exception:rolled_back=False
    emit('HOLD_PATCH_ERROR',patch_applied=promoted,
         rolled_back=rolled_back,download_started=False)
finally:
    if tmp is not None and tmp.exists():tmp.unlink()
PYREMOTE
"""

def main():
    result=native_once(REMOTE)
    receipt=result.get("receipt") if isinstance(result.get("receipt"),dict) else {}
    state=receipt.get("state")
    verified=(result.get("native_ack") is True
              and result.get("key_detached") is True
              and state in ("NATIVE_HF_PATH_PATCH_VERIFIED","ALREADY_PATCHED"))
    if receipt:
        print("NATIVE_DOWNLOAD_PATH_REPAIR="+json.dumps(receipt,sort_keys=True,separators=(",",":")))
    print("NOX_V63_NATIVE_WRITE_ATTEMPTS="+str(result.get("write_attempts")))
    print("NOX_V63_NATIVE_ACK="+str(result.get("native_ack") is True).lower())
    print("NOX_V63_EPHEMERAL_KEY_DETACHED="+str(result.get("key_detached") is True).lower())
    print("NOX_V63_DOWNLOAD_HF_INTEGRATION_VERIFIED="+str(verified).lower())
    if not verified:
        print("NOX_V63_HF_STATE="+str(result.get("state","HOLD_NATIVE_UNKNOWN")))
    return 0 if verified else 2

if __name__=="__main__":raise SystemExit(main())
