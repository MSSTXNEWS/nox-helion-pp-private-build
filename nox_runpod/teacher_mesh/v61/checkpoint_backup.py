"""NOX V61: encrypted checkpoint+optimizer stream for existing NOX.

Follows the V60 verified age recipient and temporary SSH transport, but
selects all small checkpoint/optimizer assets from existing /root/nox.
No plaintext artifacts, no remote service changes, no deletion.
"""
from __future__ import annotations
import hashlib,io,json,os
from pathlib import Path
import subprocess,sys,tarfile,time,shlex
from nox_runpod.teacher_mesh.v60 import encrypted_backup as v60

RUN=Path(os.environ.get('RUNNER_TEMP','/tmp'))/'nox-v61-checkpoints'
FINAL=Path('NOX_V61_CHECKPOINT_OPTIMIZER_ENCRYPTED_20261114.tar.age')
RECEIPT=Path('NOX_V61_CHECKPOINT_OPTIMIZER_RECEIPT.json')
CANDIDATE=FINAL.with_name(FINAL.name+'.pending')
RECEIPT_PENDING=RECEIPT.with_name(RECEIPT.name+'.pending')
ATTACH_ATTEMPTED=False

REMOTE=r"""
import hashlib,io,json,os,stat,sys,tarfile
from pathlib import Path
root=Path('/root/nox')
skip={'.git','.ssh','.cache','venv','.venv','node_modules','__pycache__'}
selected=[]
for directory,dirs,files in os.walk(root,followlinks=False):
    dirs[:]=[d for d in dirs if d not in skip][:140]
    for name in files:
        low=name.lower()
        # Match the verified V58 checkpoint classifier, but leave
        # heavyweight .safetensors/GGUF to the separate cold-weights lane.
        if low.endswith(('.safetensors','.gguf')):
            continue
        if not (low.endswith(('.pt','.pth','.ckpt')) or
                'checkpoint' in low or 'optimizer' in low or low.startswith('optim.')):
            continue
        p=Path(directory)/name
        try:
            info=p.lstat()
            if not stat.S_ISREG(info.st_mode):continue
            if info.st_size>2_000_000_000:raise SystemExit(28)
        except OSError:continue
        selected.append((p,info.st_size))
if len(selected)<10 or len(selected)>90:raise SystemExit(21)
if sum(s for p,s in selected)>1_300_000_000:raise SystemExit(22)
selected.sort(key=lambda x:str(x[0]))
# Hash in bounded chunks: a checkpoint can approach 1.3 GB while the
# native host has only a narrow cgroup RAM margin.
def sha256_path(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()
manifest=[]
for p,size in selected:
    rel=p.relative_to(root)
    sha=sha256_path(p)
    manifest.append({'path':'NOX_CHECKPOINTS/'+str(rel),'size_bytes':size,'sha256':sha})
raw=json.dumps({'schema':'NOX_V61_CHECKPOINT_OPTIMIZER_MANIFEST_V1',
                'origin_instance_id':60509551,
                'files':manifest,'original_files_deleted':False},
               sort_keys=True,separators=(',',':')).encode()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
    for p,_ in selected:
        archive.add(p,arcname='NOX_CHECKPOINTS/'+str(p.relative_to(root)),recursive=False)
    entry=tarfile.TarInfo('RESTORE_MANIFEST.json')
    entry.size=len(raw);entry.mode=0o600;entry.mtime=0
    archive.addfile(entry,io.BytesIO(raw))
sys.stdout.flush()
# Snapshot safety: abort if the source changed while it was being streamed.
for (p,_),saved in zip(selected,manifest):
    if not p.exists() or sha256_path(p)!=saved['sha256']:
        raise SystemExit(31)
"""



def verify_plaintext_tar(plaintext:bytes)->dict:
    """Strict one-to-one manifest↔regular-file audit, without filesystem extraction.

    Independent synthetic tar tests can call this without age, SSH, private keys
    or a native checkpoint. This does not prove a production backup was restored.
    """
    import re
    with tarfile.open(fileobj=io.BytesIO(plaintext),mode='r:gz') as archive:
        members=archive.getmembers()
        if not 11<=len(members)<=91:
            raise RuntimeError('HOLD_TAR_MEMBER_COUNT')
        names=[m.name for m in members]
        if len(names)!=len(set(names)):
            raise RuntimeError('HOLD_TAR_DUPLICATE_MEMBER')
        # extractfile() follows tar symlinks/hardlinks, so validate types FIRST.
        if any(not m.isfile() for m in members):
            raise RuntimeError('HOLD_TAR_UNSAFE_MEMBER')
        by_name={m.name:m for m in members}
        manifest_member=by_name.get('RESTORE_MANIFEST.json')
        if manifest_member is None or not 0<manifest_member.size<=1_000_000:
            raise RuntimeError('HOLD_TAR_MANIFEST_MISSING_OR_OVERSIZED')
        with archive.extractfile(manifest_member) as f:
            try:
                obj=json.loads(f.read().decode('utf-8'))
            except (UnicodeError,ValueError) as exc:
                raise RuntimeError('HOLD_MANIFEST_JSON') from exc
        if (not isinstance(obj,dict) or
            obj.get('schema')!='NOX_V61_CHECKPOINT_OPTIMIZER_MANIFEST_V1' or
            obj.get('origin_instance_id')!=60509551 or
            obj.get('original_files_deleted') is not False):
            raise RuntimeError('HOLD_MANIFEST_SCHEMA')
        items=obj.get('files')
        if not isinstance(items,list) or not 10<=len(items)<=90:
            raise RuntimeError('HOLD_UNEXPECTED_ITEMS')
        expected={'RESTORE_MANIFEST.json'}
        checked=[]
        total=0
        for item in items:
            if not isinstance(item,dict) or set(item)!={'path','size_bytes','sha256'}:
                raise RuntimeError('HOLD_MANIFEST_RECORD')
            name=item['path']
            if (not isinstance(name,str) or len(name)>4096 or
                name.startswith('/') or '\\' in name or '\x00' in name or
                len(name.split('/'))<2 or name.split('/')[0]!='NOX_CHECKPOINTS' or
                any(x in ('','.', '..') for x in name.split('/')[1:])):
                raise RuntimeError('HOLD_MANIFEST_PATH')
            if name in expected:
                raise RuntimeError('HOLD_MANIFEST_DUPLICATE_PATH')
            size=item['size_bytes']; digest=item['sha256']
            if (type(size) is not int or size<0 or size>2_000_000_000 or
                not isinstance(digest,str) or
                re.fullmatch('[0-9a-f]{64}',digest) is None):
                raise RuntimeError('HOLD_MANIFEST_RECORD')
            total+=size
            if total>1_300_000_000:
                raise RuntimeError('HOLD_MANIFEST_TOTAL_BYTES')
            expected.add(name)
            checked.append((name,size,digest))
        # The original backup writer emits exactly N regular files + manifest.
        # Unlisted files, missing files, duplicated names and link entries HOLD.
        if set(names)!=expected or len(names)!=len(expected):
            raise RuntimeError('HOLD_TAR_MEMBER_COVERAGE')
        for name,expected_size,digest in checked:
            member=by_name[name]
            if member.size!=expected_size:
                raise RuntimeError('HOLD_CHECKPOINT_RESTORE_HASH')
            sha=hashlib.sha256();count=0
            with archive.extractfile(member) as f:
                while True:
                    part=f.read(1048576)
                    if not part:break
                    count+=len(part)
                    sha.update(part)
            if count!=expected_size or sha.hexdigest()!=digest:
                raise RuntimeError('HOLD_CHECKPOINT_RESTORE_HASH')
        # Archive hashes prove bytes, not optimizer/RNG compatibility or a live step.
        # Names are hints only: a .pt file can contain arbitrary pickled objects.
        names_lower = [name.rsplit('/', 1)[-1].lower() for name, _, _ in checked]
        resume_name_hints = {
            'optimizer': any('optimizer' in name or name.startswith('optim.') for name in names_lower),
            'rng': any('rng' in name or 'random_state' in name for name in names_lower),
            'scaler': any('scaler' in name or 'grad_scaler' in name for name in names_lower),
        }
        return {'count':len(checked),'total_bytes':total,
                'resume_name_hints':resume_name_hints,
                'functional_optimizer_restore_verified':False}


def verify_plaintext_tar_stream(source)->dict:
    """Validate a decrypted gzip tar sequentially, keeping plaintext off disk/RAM.

    The V61 exporter writes regular checkpoint files then RESTORE_MANIFEST.json.
    Read at most 1 MiB per file chunk and compare the final manifest to observed
    bytes; never load the up-to-1.3-GB decrypted archive with capture_output.
    """
    class DigestReader:
        def __init__(self,raw):
            self.raw=raw
            self.digest=hashlib.sha256()
            self.total=0

        def read(self,n=1048576):
            if type(n) is not int or n<=0:
                raise RuntimeError('HOLD_TAR_UNBOUNDED_READ')
            part=self.raw.read(min(n,1048576))
            self.total+=len(part)
            if self.total>1_400_000_000:
                raise RuntimeError('HOLD_TAR_COMPRESSED_SIZE_LIMIT')
            self.digest.update(part)
            return part

    import re
    reader=DigestReader(source)
    found={}
    manifest=None
    total=0
    count=0
    try:
        with tarfile.open(fileobj=reader,mode='r|gz') as archive:
            for member in archive:
                count+=1
                if count>91:
                    raise RuntimeError('HOLD_TAR_MEMBER_COUNT')
                if not member.isfile():
                    raise RuntimeError('HOLD_TAR_UNSAFE_MEMBER')
                name=member.name
                if name=='RESTORE_MANIFEST.json':
                    if manifest is not None or not 0<member.size<=1_000_000:
                        raise RuntimeError('HOLD_TAR_MANIFEST_MISSING_OR_OVERSIZED')
                    with archive.extractfile(member) as input_file:
                        try:
                            manifest=json.loads(input_file.read().decode('utf-8'))
                        except (UnicodeError,ValueError) as exc:
                            raise RuntimeError('HOLD_MANIFEST_JSON') from exc
                    continue
                if manifest is not None:
                    raise RuntimeError('HOLD_TAR_MANIFEST_NOT_LAST')
                if (not isinstance(name,str) or len(name)>4096 or
                    name.startswith('/') or '\\' in name or '\x00' in name or
                    name.split('/')[0]!='NOX_CHECKPOINTS' or
                    len(name.split('/'))<2 or
                    any(part in ('','.', '..') for part in name.split('/')[1:])):
                    raise RuntimeError('HOLD_MANIFEST_PATH')
                if name in found:
                    raise RuntimeError('HOLD_TAR_DUPLICATE_MEMBER')
                if member.size<0 or member.size>2_000_000_000:
                    raise RuntimeError('HOLD_MANIFEST_RECORD')
                total+=member.size
                if total>1_300_000_000:
                    raise RuntimeError('HOLD_MANIFEST_TOTAL_BYTES')
                digest=hashlib.sha256()
                bytes_read=0
                with archive.extractfile(member) as input_file:
                    while True:
                        chunk=input_file.read(1048576)
                        if not chunk:
                            break
                        digest.update(chunk)
                        bytes_read+=len(chunk)
                if bytes_read!=member.size:
                    raise RuntimeError('HOLD_CHECKPOINT_RESTORE_HASH')
                found[name]=(member.size,digest.hexdigest())
    except (tarfile.TarError,EOFError,OSError) as exc:
        raise RuntimeError('HOLD_TAR_STREAM_INVALID') from exc
    # tarfile stops at the end-of-archive marker; hash remaining padding/trailer
    # too, so the digest exactly matches the old full decrypted tar.gz SHA.
    while reader.read(1048576):
        pass
    if not 11<=count<=91 or manifest is None or not 10<=len(found)<=90:
        raise RuntimeError('HOLD_TAR_MEMBER_COUNT')
    if (not isinstance(manifest,dict) or
        manifest.get('schema')!='NOX_V61_CHECKPOINT_OPTIMIZER_MANIFEST_V1' or
        manifest.get('origin_instance_id')!=60509551 or
        manifest.get('original_files_deleted') is not False):
        raise RuntimeError('HOLD_MANIFEST_SCHEMA')
    items=manifest.get('files')
    if not isinstance(items,list) or len(items)!=len(found):
        raise RuntimeError('HOLD_TAR_MEMBER_COVERAGE')
    expected=set()
    for item in items:
        if not isinstance(item,dict) or set(item)!={'path','size_bytes','sha256'}:
            raise RuntimeError('HOLD_MANIFEST_RECORD')
        name=item['path'];size=item['size_bytes'];digest=item['sha256']
        if (not isinstance(name,str) or name in expected or name not in found or
            type(size) is not int or size<0 or
            not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None):
            raise RuntimeError('HOLD_MANIFEST_RECORD')
        expected.add(name)
        if found[name]!=(size,digest):
            raise RuntimeError('HOLD_CHECKPOINT_RESTORE_HASH')
    if set(found)!=expected:
        raise RuntimeError('HOLD_TAR_MEMBER_COVERAGE')
    names_lower=[name.rsplit('/',1)[-1].lower() for name in found]
    hints={
        'optimizer':any('optimizer' in name or name.startswith('optim.') for name in names_lower),
        'rng':any('rng' in name or 'random_state' in name for name in names_lower),
        'scaler':any('scaler' in name or 'grad_scaler' in name for name in names_lower),
    }
    return {'count':len(found),'total_bytes':total,'resume_name_hints':hints,
            'functional_optimizer_restore_verified':False,
            'plaintext_sha256':reader.digest.hexdigest()}


def verify(encrypted:Path,test_identity:Path)->dict:
    # The legacy subprocess.run(capture_output=True) retained up to 1.3 GB of
    # plaintext. Consume age's stdout as a pipe, without disk spooling.
    import threading
    process=subprocess.Popen(['age','-d','-i',str(test_identity),str(encrypted)],
                             stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    timed_out=threading.Event()
    def abort_timeout():
        if process.poll() is None:
            timed_out.set()
            process.kill()
    timer=threading.Timer(180,abort_timeout)
    timer.daemon=True
    timer.start()
    try:
        try:
            with process.stdout:
                verified=verify_plaintext_tar_stream(process.stdout)
        except Exception:
            if process.poll() is None:
                process.kill()
            raise
        code=process.wait(timeout=15)
        if timed_out.is_set():
            raise RuntimeError('HOLD_TEST_RESTORE_TIMEOUT')
        if code:
            raise RuntimeError('HOLD_TEST_RESTORE_DECRYPT')
        return verified
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=15)


def classify_ssh_timeout(rc: int, stderr: bytes) -> str | None:
    """Retry only an OpenSSH TCP *connect* timeout before a session exists.

    A generic 'timed out' from a running remote exporter is UNKNOWN, because
    the checkpoint stream or another remote effect may still be in flight.
    """
    if not isinstance(stderr, bytes) or b'timed out' not in stderr.lower():
        return None
    detail = stderr.lower()
    if (rc == 255 and b'ssh: connect to host ' in detail and
        b' port ' in detail and b': connection timed out' in detail):
        return 'SSH_CONNECT_TIMEOUT_PRE_EXEC'
    return 'SSH_TIMEOUT_REMOTE_STATE_UNKNOWN'


def transport_retry_delay(error_class: str, attempt_index: int) -> int | None:
    """No replay after session establishment or unknown remote outcome."""
    if error_class != 'SSH_CONNECT_TIMEOUT_PRE_EXEC' or type(attempt_index) is not int:
        return None
    return (10, 30)[attempt_index] if 0 <= attempt_index < 2 else None


def publish_verified_backup(candidate:Path, final:Path, receipt_path:Path, receipt:dict)->None:
    """Promote only a successfully verified candidate; preserve prior evidence.

    Never replace existing ciphertext/receipt, including when a previous run
    ended ambiguously. Both staged files live beside their destination.
    """
    if final.exists() or receipt_path.exists():
        raise RuntimeError('HOLD_V61_EXISTING_PUBLISHED_ARTIFACT')
    if not candidate.is_file():
        raise RuntimeError('HOLD_V61_CANDIDATE_MISSING')
    # An existence check followed by Path.replace() is not a CAS: a second
    # publisher may create FINAL between the check and replacement. Hard-link
    # publication fails atomically if its destination already exists.
    import tempfile
    pending=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',
                prefix=receipt_path.name+'.pending.',
                dir=str(receipt_path.parent),delete=False) as stream:
            pending=Path(stream.name)
            stream.write(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(candidate,final)
        except FileExistsError as exc:
            raise RuntimeError('HOLD_V61_PUBLISH_RACE') from exc
        # Receipt is the last publication marker; a failed second link
        # leaves partial evidence for owner reconciliation, never overwrites.
        try:
            os.link(pending,receipt_path)
        except FileExistsError as exc:
            raise RuntimeError('HOLD_V61_RECEIPT_RACE') from exc
        candidate.unlink()
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def run():
    global ATTACH_ATTEMPTED
    # V61 is an owner-reviewed one-shot: never erase a prior published proof.
    if FINAL.exists() or RECEIPT.exists():
        raise RuntimeError('HOLD_V61_EXISTING_PUBLISHED_ARTIFACT')
    owner,fingerprint=v60.existing_owner_recipient()
    host,port=v60.live_direct_route()
    v60.RUN=RUN
    RUN.mkdir(mode=0o700,parents=True,exist_ok=True)
    identity=RUN/'restore_test.agekey'
    subprocess.run(['age-keygen','-o',str(identity)],
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=10)
    identity.chmod(0o600)
    r=subprocess.run(['age-keygen','-y',str(identity)],capture_output=True,text=True,timeout=10)
    if r.returncode or not r.stdout.strip().startswith('age1'):
        raise RuntimeError('HOLD_RECIPIENT_KEY')
    recipients=RUN/'recipients'
    recipients.write_text(owner+'\n'+r.stdout.strip()+'\n')
    ATTACH_ATTEMPTED=True
    v60.attach_temporary_key()
    known=RUN/'known_hosts'
    try:
        time.sleep(12)
        for i in range(3):
            CANDIDATE.unlink(missing_ok=True)
            command=['ssh','-T','-i',str(v60.conn.KEY),'-p',str(port),
                     '-o','BatchMode=yes','-o','IdentitiesOnly=yes',
                     '-o','ConnectTimeout=10',
                     '-o','StrictHostKeyChecking=accept-new',
                     '-o','UserKnownHostsFile='+str(known),
                     'root@'+host,'python3 -c '+shlex.quote(REMOTE)]
            ssh=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            encrypted=subprocess.Popen(['age','-R',str(recipients),'-o',str(CANDIDATE)],
                stdin=ssh.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            ssh.stdout.close()
            try:
                _,_=encrypted.communicate(timeout=240)
                rc=ssh.wait(timeout=15)
            except subprocess.TimeoutExpired:
                ssh.kill();encrypted.kill()
                ssh.communicate();encrypted.communicate()
                raise RuntimeError('HOLD_CHECKPOINT_STREAM_TIMEOUT')
            if rc==0 and encrypted.returncode==0 and CANDIDATE.is_file() and CANDIDATE.stat().st_size>1024:
                break
            emsg=(ssh.stderr.read(10000) if ssh.stderr is not None else b'').lower()
            if rc==1 and b'traceback' in emsg:
                exception_names=('TypeError','ValueError','NameError','AttributeError',
                    'FileNotFoundError','PermissionError','RuntimeError','OSError',
                    'IsADirectoryError','BrokenPipeError','MemoryError','KeyError',
                    'tarfile.ReadError','tarfile.TarError')
                kind=next((k for k in exception_names if (k.lower()+':').encode() in emsg), 'UNKNOWN_EXCEPTION')
                import re
                line_match=re.findall(rb'line (\d+)',emsg)
                last_line=line_match[-1].decode() if line_match else 'UNKNOWN'
                print('NOX_V61_REMOTE_EXCEPTION_CLASS='+kind)
                print('NOX_V61_REMOTE_EXCEPTION_LINE='+last_line)
                raise RuntimeError('HOLD_REMOTE_CHECKPOINT_SCRIPT_EXCEPTION')
            if rc==21:cls='CHECKPOINT_FILE_COUNT'
            elif rc==22:cls='CHECKPOINT_TOTAL_SIZE_LIMIT'
            elif rc==28:cls='CHECKPOINT_ITEM_SIZE_LIMIT'
            elif rc==31:cls='CHECKPOINT_CHANGED_DURING_STREAM'
            elif b'permission denied' in emsg:cls='SSH_AUTH_DENIED'
            elif (timeout_class := classify_ssh_timeout(rc, emsg)) is not None:cls=timeout_class
            elif b'traceback' in emsg:cls='REMOTE_PYTHON'
            else:cls='OTHER'
            print('NOX_V61_ATTEMPT_'+str(i+1)+'_CLASS='+cls)
            print('NOX_V61_ATTEMPT_'+str(i+1)+'_SSH_RC='+str(rc))
            print('NOX_V61_ATTEMPT_'+str(i+1)+'_AGE_RC='+str(encrypted.returncode))
            print('NOX_V61_ATTEMPT_'+str(i+1)+'_CIPHERTEXT_BYTES='+str(CANDIDATE.stat().st_size if CANDIDATE.exists() else 0))
            delay = transport_retry_delay(cls, i)
            if delay is None:
                raise RuntimeError('HOLD_CHECKPOINT_STREAM_' + cls)
            time.sleep(delay)

        restored=verify(CANDIDATE,identity)
        receipt={
            'schema':'NOX_V61_ENCRYPTED_CHECKPOINT_RECEIPT_V1',
            'instance_id':60509551,
            'ciphertext_sha256':v60.sha256_file(CANDIDATE),
            'ciphertext_bytes':CANDIDATE.stat().st_size,
            'checkpoint_optimizer_files':restored['count'],
            'original_total_bytes':restored['total_bytes'],
            'restored_plain_sha256':restored['plaintext_sha256'],
            'archive_hash_integrity_verified':True,
            'resume_name_hints_only':restored['resume_name_hints'],
            'functional_optimizer_restore_verified':False,
            'optimizer_step_delta_verified':False,
            'native_training_admission':'HOLD_RESTORE_AND_RESOURCE_UNVERIFIED',
            'temporary_age_test_restore':'PASS',
            'existing_ssh_owner_recipient_sha256':fingerprint,
            'owner_private_key_decryption_tested':False,
            'remote_cleanup_performed':False,
            'live_training_restarted':False,
        }
        publish_verified_backup(CANDIDATE,FINAL,RECEIPT,receipt)
        print('NOX_V61_CHECKPOINT_COUNT='+str(restored['count']))
        print('NOX_V61_SOURCE_BYTES='+str(restored['total_bytes']))
        print('NOX_V61_CIPHERTEXT_SHA256='+receipt['ciphertext_sha256'])
        print('NOX_V61_TEST_RESTORE=PASS_ALL_SHA')
    finally:
        try:
            if not v60.conn.cleanup():
                raise RuntimeError('HOLD_SSH_KEY_CLEANUP')
            print('NOX_V61_TEMP_KEY_DETACH=VERIFIED')
        finally:
            identity.unlink(missing_ok=True)
            recipients.unlink(missing_ok=True)


if __name__=='__main__':
    try:run()
    except Exception as exc:
        print(str(exc) if str(exc).startswith('HOLD_') else 'HOLD_V61_UNKNOWN',file=sys.stderr)
        try:
            if ATTACH_ATTEMPTED and v60.conn.TRACK.exists():v60.conn.cleanup()
        except Exception:print('HOLD_V61_KEY_CLEANUP',file=sys.stderr)
        if ATTACH_ATTEMPTED:
            CANDIDATE.unlink(missing_ok=True)
            RECEIPT_PENDING.unlink(missing_ok=True)
        raise SystemExit(2)
