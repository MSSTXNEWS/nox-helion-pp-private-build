"""NOX V69: offsite encrypt one measured cold archive staged through Vast RAM.

Only the exact read-only incoming ZIP identified by native full SHA is streamed
via RAM tmpfs to GitHub runner, encrypted to EXISTING owner's age SSH recipient.
The archive is NOT deleted on Vast; no public model, OneHost, S03 or trainer
is changed. A disposable second recipient enables independent SHA verification
of ciphertext restore without exporting secrets.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from nox_runpod.teacher_mesh.v60 import encrypted_backup as v60

SOURCE_BYTES=85_218_466
SOURCE_SHA="171c1b7894391ead3d376ae0e375fb34991854eeb3cce2aa04f2c28a301000c5"
SOURCE_AUDIT_RUN="https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43622575039"
OWNER_V60_RECIPIENT_FINGERPRINT="4a9cab493ae0f51145c0609271022a185b9310b6432ec1914b5b0ce89b7571a5"
OUTPUT=Path("NOX_V69_COLD_INCOMING_85218466_20261114.zip.age")
RECEIPT=Path("NOX_V69_COLD_INCOMING_85218466_RECEIPT.json")
RUN=Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "nox-v69-owner-cipher"

REMOTE=r"""
import hashlib,os,stat,sys,tempfile,time
from pathlib import Path
root=Path('/root/nox/incoming_t800u')
size=85218466
expected='171c1b7894391ead3d376ae0e375fb34991854eeb3cce2aa04f2c28a301000c5'
candidates=[]
for base,dirs,files in os.walk(root,followlinks=False):
    dirs[:]=[d for d in dirs if not (Path(base)/d).is_symlink()][:75]
    for name in files:
        p=Path(base)/name
        if p.suffix!='.zip':continue
        try:
            st=p.lstat()
            if stat.S_ISREG(st.st_mode) and st.st_size==size and st.st_nlink==1:
                candidates.append((p,st))
        except OSError:continue
        if len(candidates)>1:break
    if len(candidates)>1:break
if len(candidates)!=1:sys.exit(31)
path,meta=candidates[0]
# Do not read a live file or alter the active user-facing NOX stack.
for pid in os.listdir('/proc'):
    if not pid.isdigit():continue
    try:
        for fd in list((Path('/proc')/pid/'fd').iterdir())[:240]:
            try:
                if os.readlink(fd).removesuffix(' (deleted)')==str(path):sys.exit(35)
            except (OSError,ValueError):pass
    except OSError:pass
vfs=os.statvfs('/dev/shm')
if vfs.f_bavail*vfs.f_frsize < size*3:sys.exit(34)
# Low-priority stream. TemporaryFile is unlinked from the RAM filesystem
# immediately; its contents disappear on close or process exit.
try:os.nice(10)
except (OSError,PermissionError):pass
with tempfile.TemporaryFile(mode='w+b',dir='/dev/shm') as memory:
    h=hashlib.sha256()
    length=0
    with path.open('rb') as source:
        while True:
            block=source.read(1024*1024)
            if not block:break
            h.update(block)
            memory.write(block)
            length+=len(block)
            time.sleep(0.015)
    after=path.stat()
    if (length!=size or h.hexdigest()!=expected or
        after.st_size!=meta.st_size or after.st_mtime_ns!=meta.st_mtime_ns or
        after.st_ino!=meta.st_ino):sys.exit(33)
    memory.flush()
    memory.seek(0)
    while True:
        block=memory.read(1024*1024)
        if not block:break
        sys.stdout.buffer.write(block)
        sys.stdout.buffer.flush()
        time.sleep(0.025)
"""
def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(2*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def test_decrypt(encrypted:Path,identity:Path)->tuple[int,str]:
    cmd=['age','-d','-i',str(identity),str(encrypted)]
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    length=0;h=hashlib.sha256()
    try:
        assert p.stdout is not None
        for piece in iter(lambda:p.stdout.read(2*1024*1024),b''):
            h.update(piece);length+=len(piece)
            if length>SOURCE_BYTES:
                p.kill()
                raise RuntimeError('HOLD_RESTORE_OVERSIZE')
        if p.wait(timeout=30)!=0:raise RuntimeError('HOLD_AGE_RESTORE_FAILED')
    finally:
        if p.stdout:p.stdout.close()
        if p.stderr:p.stderr.close()
    return length,h.hexdigest()

def existing_owner_recipient_pinned()->tuple[str,str]:
    """Identify EXACT V60 owner SSH recipient, never choose a random key."""
    records=v60.conn.keys(os.environ['NOX2'])
    candidates=[]
    for item in records:
        raw=str(item.get('public_key','')).strip()
        parts=raw.split()
        if len(parts)<2 or parts[0] not in ('ssh-ed25519','ssh-rsa'):
            continue
        recipient=' '.join(parts[:2])
        fp=hashlib.sha256(recipient.encode()).hexdigest()
        if fp==OWNER_V60_RECIPIENT_FINGERPRINT:
            candidates.append(recipient)
    if len(candidates)!=1:
        raise RuntimeError('HOLD_ORIGINAL_V60_OWNER_KEY_NOT_PRESENT_OR_AMBIGUOUS')
    return candidates[0],OWNER_V60_RECIPIENT_FINGERPRINT

def run()->None:
    if not os.environ.get('NOX2'):raise RuntimeError('HOLD_NOX2')
    owner,owner_fingerprint=existing_owner_recipient_pinned()
    host,port=v60.live_direct_route()
    RUN.mkdir(mode=0o700,parents=True,exist_ok=True)
    identity=RUN/'test_identity.agekey'
    subprocess.run(['age-keygen','-o',str(identity)],stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL,check=True,timeout=12)
    identity.chmod(0o600)
    pub=subprocess.run(['age-keygen','-y',str(identity)],capture_output=True,text=True,timeout=12,check=True)
    if not pub.stdout.startswith('age1'):raise RuntimeError('HOLD_TEST_RECIPIENT')
    recipients=RUN/'recipients'
    recipients.write_text(owner+'\n'+pub.stdout.strip()+'\n')
    recipients.chmod(0o600)
    v60.RUN=RUN
    known=RUN/'known_hosts'
    done=False
    try:
        v60.attach_temporary_key()
        for i in range(5):
            OUTPUT.unlink(missing_ok=True)
            argv=['ssh','-T','-n','-i',str(v60.conn.KEY),'-p',str(port),
                '-o','BatchMode=yes','-o','IdentitiesOnly=yes',
                '-o','ConnectTimeout=12','-o','StrictHostKeyChecking=accept-new',
                '-o','UserKnownHostsFile='+str(known),
                'root@'+host,'python3 -c '+shlex.quote(REMOTE)]
            source=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            encryption=subprocess.Popen(['age','-R',str(recipients),'-o',str(OUTPUT)],
                stdin=source.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            assert source.stdout is not None
            source.stdout.close()
            try:
                _,ageerr=encryption.communicate(timeout=240)
                code=source.wait(timeout=25)
            except subprocess.TimeoutExpired:
                source.kill();encryption.kill()
                source.communicate();encryption.communicate()
                raise RuntimeError('HOLD_STREAM_TIMEOUT')
            stderr=source.stderr.read(14000) if source.stderr else b''
            if code==0 and encryption.returncode==0 and OUTPUT.is_file() and OUTPUT.stat().st_size>1_000_000:
                done=True
                break
            if code in (31,33,34,35):
                raise RuntimeError({31:'HOLD_SOURCE_AMBIGUOUS',33:'HOLD_SOURCE_CHANGED_OR_SHA',
                    34:'HOLD_RAM_BUFFER_INSUFFICIENT',35:'HOLD_SOURCE_OPEN_BY_PROCESS'}[code])
            cls=('AUTH' if b'permission denied' in stderr.lower() else
                 'NETWORK' if b'timed out' in stderr.lower() else
                 'REMOTE' if code not in (255,0) else 'TRANSPORT')
            print('NOX_V69_OFFLOAD_RETRY_CLASS='+cls)
            time.sleep(6)
        if not done:raise RuntimeError('HOLD_ENCRYPTED_STREAM_NOT_VERIFIED')
        length,digest=test_decrypt(OUTPUT,identity)
        if length!=SOURCE_BYTES or digest!=SOURCE_SHA:raise RuntimeError('HOLD_OFFSITE_RESTORE_HASH')
        record={
            'schema':'NOX_V69_ONE_COLD_OWNER_ENCRYPTED_OFFSITE_V1',
            'instance_id':60509551,
            'source_audit_run':SOURCE_AUDIT_RUN,
            'source_bytes':SOURCE_BYTES,
            'source_sha256':SOURCE_SHA,
            'ciphertext_file':OUTPUT.name,
            'ciphertext_bytes':OUTPUT.stat().st_size,
            'ciphertext_sha256':sha(OUTPUT),
            'owner_ssh_recipient_fingerprint_sha256':owner_fingerprint,
            'temporary_test_identity_decryption_verified':True,
            'restored_plain_sha256_matches_source':True,
            'owner_private_key_decryption_verified':False,
            'remote_ram_used_as_volatile_staging':True,
            'remote_ram_staging_closed':True,
            'remote_source_deleted':False,
            'active_prime_model_or_s03_changed':False,
            'trainer_or_teacher_restarted':False,
            'offsite_drive_upload_verified':False,
            'user_pc_copy_verified':False
        }
        RECEIPT.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
        print('NOX_V69_AGE_CIPHERTEXT_SHA256='+record['ciphertext_sha256'])
        print('NOX_V69_AGE_CIPHERTEXT_BYTES='+str(record['ciphertext_bytes']))
        print('NOX_V69_RESTORE_TEST_SHA256=PASS')
        print('NOX_V69_OWNER_ENCRYPTED_OFFLOAD=PASS_RUNNER')
    finally:
        try:
            if not v60.conn.cleanup():
                raise RuntimeError('HOLD_TEMP_SSH_KEY_NOT_REVOKED')
            print('NOX_V69_TEMP_SSH_KEY_REVOKED_VERIFIED=true')
        finally:
            recipients.unlink(missing_ok=True)
            identity.unlink(missing_ok=True)

if __name__=='__main__':
    try:run()
    except Exception as exc:
        OUTPUT.unlink(missing_ok=True)
        RECEIPT.unlink(missing_ok=True)
        msg=str(exc)
        print(msg if msg.startswith('HOLD_') else 'HOLD_V69_OFFLOAD_ERROR',file=sys.stderr)
        try:
            if v60.conn.TRACK.exists() and not v60.conn.cleanup():
                print('HOLD_TEMP_SSH_KEY_CLEANUP',file=sys.stderr)
        except Exception:
            print('HOLD_TEMP_SSH_KEY_CLEANUP',file=sys.stderr)
        raise SystemExit(2)
