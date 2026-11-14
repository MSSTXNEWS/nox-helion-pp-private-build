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
manifest=[]
for p,size in selected:
    rel=p.relative_to(root)
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
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
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=saved['sha256']:
        raise SystemExit(31)
"""


def verify(encrypted:Path,test_identity:Path)->dict:
    p=subprocess.run(['age','-d','-i',str(test_identity),str(encrypted)],
                     capture_output=True,timeout=180)
    if p.returncode:raise RuntimeError('HOLD_TEST_RESTORE_DECRYPT')
    with tarfile.open(fileobj=io.BytesIO(p.stdout),mode='r:gz') as archive:
        obj=json.loads(archive.extractfile('RESTORE_MANIFEST.json').read())
        if obj.get('schema')!='NOX_V61_CHECKPOINT_OPTIMIZER_MANIFEST_V1':
            raise RuntimeError('HOLD_MANIFEST_SCHEMA')
        items=obj['files']
        if not 10<=len(items)<=90:raise RuntimeError('HOLD_UNEXPECTED_ITEMS')
        checked=0
        for record in items:
            f=archive.extractfile(record['path'])
            if f is None:raise RuntimeError('HOLD_MISSING_MEMBER')
            h=hashlib.sha256();size=0
            while True:
                b=f.read(1048576)
                if not b:break
                size+=len(b);h.update(b)
            if h.hexdigest()!=record['sha256'] or size!=record['size_bytes']:
                raise RuntimeError('HOLD_CHECKPOINT_RESTORE_HASH')
            checked+=1
        return {'count':checked,'plaintext_sha256':hashlib.sha256(p.stdout).hexdigest(),
                'total_bytes':sum(x['size_bytes'] for x in items)}


def run():
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
    v60.attach_temporary_key()
    known=RUN/'known_hosts'
    try:
        time.sleep(12)
        for i in range(10):
            FINAL.unlink(missing_ok=True)
            command=['ssh','-T','-i',str(v60.conn.KEY),'-p',str(port),
                     '-o','BatchMode=yes','-o','IdentitiesOnly=yes',
                     '-o','ConnectTimeout=10',
                     '-o','StrictHostKeyChecking=accept-new',
                     '-o','UserKnownHostsFile='+str(known),
                     'root@'+host,'python3 -c '+shlex.quote(REMOTE)]
            ssh=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            encrypted=subprocess.Popen(['age','-R',str(recipients),'-o',str(FINAL)],
                stdin=ssh.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            ssh.stdout.close()
            try:
                _,_=encrypted.communicate(timeout=240)
                rc=ssh.wait(timeout=15)
            except subprocess.TimeoutExpired:
                ssh.kill();encrypted.kill()
                ssh.communicate();encrypted.communicate()
                raise RuntimeError('HOLD_CHECKPOINT_STREAM_TIMEOUT')
            if rc==0 and encrypted.returncode==0 and FINAL.is_file() and FINAL.stat().st_size>1024:
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
            elif b'timed out' in emsg:cls='SSH_NETWORK_TIMEOUT'
            elif b'traceback' in emsg:cls='REMOTE_PYTHON'
            else:cls='OTHER'
            print('NOX_V61_ATTEMPT_'+str(i+1)+'_CLASS='+cls)
            print('NOX_V61_ATTEMPT_'+str(i+1)+'_SSH_RC='+str(rc))
            print('NOX_V61_ATTEMPT_'+str(i+1)+'_AGE_RC='+str(encrypted.returncode))
            print('NOX_V61_ATTEMPT_'+str(i+1)+'_CIPHERTEXT_BYTES='+str(FINAL.stat().st_size if FINAL.exists() else 0))
            time.sleep(5)
        else:
            raise RuntimeError('HOLD_CHECKPOINT_STREAM_TRANSPORT')
        restored=verify(FINAL,identity)
        receipt={
            'schema':'NOX_V61_ENCRYPTED_CHECKPOINT_RECEIPT_V1',
            'instance_id':60509551,
            'ciphertext_sha256':v60.sha256_file(FINAL),
            'ciphertext_bytes':FINAL.stat().st_size,
            'checkpoint_optimizer_files':restored['count'],
            'original_total_bytes':restored['total_bytes'],
            'restored_plain_sha256':restored['plaintext_sha256'],
            'temporary_age_test_restore':'PASS',
            'existing_ssh_owner_recipient_sha256':fingerprint,
            'owner_private_key_decryption_tested':False,
            'remote_cleanup_performed':False,
            'live_training_restarted':False,
        }
        RECEIPT.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
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
            if v60.conn.TRACK.exists():v60.conn.cleanup()
        except Exception:print('HOLD_V61_KEY_CLEANUP',file=sys.stderr)
        FINAL.unlink(missing_ok=True)
        raise SystemExit(2)
