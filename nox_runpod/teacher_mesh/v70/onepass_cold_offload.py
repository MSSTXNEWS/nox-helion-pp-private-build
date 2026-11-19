"""NOX V70 single-action ONEPASS: 3 cold archives → volatile RAM → owner age encryption.

Existing V51/V60 SSH bridge, no new daemon or chat. Existing V60 owner SSH
recipient pinned to the same SHA used in the verified V69 transfer. No
deletion or model/OneHost/S03 access. Split ciphertext to six ~70 MB
GitHub artifacts, then use authenticated Google Drive connector to upload.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time

from nox_runpod.teacher_mesh.v60 import encrypted_backup as v60
from nox_runpod.teacher_mesh.v69.encrypted_single_zip_offload import (
    existing_owner_recipient_pinned,
)

RUN = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "nox-v70-onepass-cold"
ENC = Path("NOX_V70_COLD_3_ENCRYPTED_20261114.tar.age")
RECEIPT = Path("NOX_V70_COLD_3_ENCRYPTED_RECEIPT.json")
INDEX = Path("NOX_V70_PARTS_INDEX.json")
PARTS_DIR = Path("split")
CHUNK_BYTES = 70_000_000
EXPECTED = {
    "BACKUP_1": (165_692_771, ".gz"),
    "BACKUP_2": (164_610_213, ".gz"),
    "INCOMING_2": (85_218_272, ".zip"),
}
TOTAL = sum(v[0] for v in EXPECTED.values())
REMOTE = r'''
import hashlib,io,json,os,stat,sys,tarfile,tempfile,time
from pathlib import Path
candidates=(
 ('BACKUP_1',Path('/root/nox/backup'),165692771,'.gz'),
 ('BACKUP_2',Path('/root/nox/backup'),164610213,'.gz'),
 ('INCOMING_2',Path('/root/nox/incoming_t800u'),85218272,'.zip'),
)
selected=[]
for label,base,size,suffix in candidates:
    matches=[]
    for root,dirs,files in os.walk(base,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(root)/d).is_symlink()][:70]
        for name in files:
            p=Path(root)/name
            if p.suffix!=suffix:continue
            try:st=p.lstat()
            except OSError:continue
            if stat.S_ISREG(st.st_mode) and st.st_size==size and st.st_nlink==1:
                matches.append((p,st))
                if len(matches)>1:break
        if len(matches)>1:break
    if len(matches)!=1:sys.exit(31)
    path,meta=matches[0]
    selected.append((label,base,path,meta))
# No training, memory or active model files are eligible for this transfer.
fds=set()
for pid in os.listdir('/proc'):
    if not pid.isdigit():continue
    try:
        for fd in list((Path('/proc')/pid/'fd').iterdir())[:190]:
            try:fds.add(os.readlink(fd).removesuffix(' (deleted)'))
            except (OSError,ValueError):pass
    except OSError:pass
if any(str(p) in fds for _,_,p,_ in selected):sys.exit(35)
space=os.statvfs('/dev/shm')
if space.f_bavail*space.f_frsize < max(i[3].st_size for i in selected)*3:
    sys.exit(34)
try:os.nice(12)
except (OSError,PermissionError):pass
records=[]
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as tf:
    for label,base,path,meta in selected:
        # Volatile immediately-unlinked RAM file; never stored in /workspace.
        with tempfile.TemporaryFile(mode='w+b',dir='/dev/shm') as memory:
            h=hashlib.sha256();length=0
            with path.open('rb') as source:
                while True:
                    block=source.read(2*1024*1024)
                    if not block:break
                    h.update(block);memory.write(block);length+=len(block)
                    time.sleep(0.015)
            after=path.stat()
            if (length!=meta.st_size or after.st_ino!=meta.st_ino or
                after.st_mtime_ns!=meta.st_mtime_ns or
                after.st_size!=meta.st_size):sys.exit(33)
            memname='COLD/'+label+path.suffix
            ti=tarfile.TarInfo(memname)
            ti.size=length;ti.mode=0o600;ti.mtime=0
            memory.seek(0)
            tf.addfile(ti,memory)
            records.append({'name':memname,'source_path_relative':str(path.relative_to(base)),
                            'source_class':label,'size_bytes':length,'sha256':h.hexdigest()})
    manifest=json.dumps({'schema':'NOX_V70_COLD_MANIFEST_V1',
        'instance_id':60509551,'no_loss':True,'source_files_deleted':False,
        'files':records},sort_keys=True,separators=(',',':')).encode()
    ti=tarfile.TarInfo('RESTORE_MANIFEST.json')
    ti.size=len(manifest);ti.mode=0o600;ti.mtime=0
    tf.addfile(ti,io.BytesIO(manifest))
sys.stdout.flush()
'''


def sha(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as fh:
        for block in iter(lambda:fh.read(2*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def test_decrypt(ciphertext:Path,identity:Path)->list[dict]:
    decrypted=subprocess.Popen(
        ['age','-d','-i',str(identity),str(ciphertext)],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    results={}
    manifest=None
    try:
        assert decrypted.stdout is not None
        with tarfile.open(fileobj=decrypted.stdout,mode='r|') as tf:
            for member in tf:
                if not member.isfile() or member.size>200_000_000:
                    raise RuntimeError('HOLD_TAR_MEMBER_INVALID')
                file=tf.extractfile(member)
                if file is None:raise RuntimeError('HOLD_MISSING_MEMBER')
                if member.name=='RESTORE_MANIFEST.json':
                    manifest=json.loads(file.read(200_000))
                    continue
                if not member.name.startswith('COLD/') or member.name in results:
                    raise RuntimeError('HOLD_UNEXPECTED_TAR_MEMBER')
                h=hashlib.sha256();size=0
                for block in iter(lambda:file.read(2*1024*1024),b''):
                    h.update(block);size+=len(block)
                    if size>200_000_000:raise RuntimeError('HOLD_STREAMED_MEMBER_OVERSIZE')
                results[member.name]=(size,h.hexdigest())
        code=decrypted.wait(timeout=40)
        if code!=0:raise RuntimeError('HOLD_TEST_AGE_DECRYPT')
    except Exception:
        decrypted.kill()
        decrypted.wait()
        raise
    finally:
        if decrypted.stdout:decrypted.stdout.close()
        if decrypted.stderr:decrypted.stderr.close()
    if not isinstance(manifest,dict) or manifest.get('schema')!='NOX_V70_COLD_MANIFEST_V1':
        raise RuntimeError('HOLD_BACKUP_MANIFEST')
    records=manifest.get('files')
    if not isinstance(records,list) or len(records)!=len(EXPECTED):
        raise RuntimeError('HOLD_MISSING_MANIFEST_ITEMS')
    for entry in records:
        label=entry.get('source_class')
        if label not in EXPECTED or entry.get('size_bytes')!=EXPECTED[label][0]:
            raise RuntimeError('HOLD_RESTORE_SIZE_OR_CLASS')
        if results.get(entry.get('name'))!=(entry.get('size_bytes'),entry.get('sha256')):
            raise RuntimeError('HOLD_RESTORE_SHA')
    if len(results)!=len(records):raise RuntimeError('HOLD_EXTRA_SOURCE_MEMBER')
    return records


def split_ciphertext()->dict:
    size=ENC.stat().st_size
    if not 415_000_000<size<435_000_000:
        raise RuntimeError('HOLD_CIPHERTEXT_UNEXPECTED_SIZE')
    parts=[]
    with ENC.open('rb') as source:
        for n in range(1,7):
            output=PARTS_DIR/f"part{n:02d}"
            output.mkdir(parents=True,exist_ok=True)
            part=output/f"NOX_V70_CIPHER.part{n:02d}"
            with part.open('wb') as writer:
                chunk=source.read(CHUNK_BYTES)
                if not chunk:raise RuntimeError('HOLD_CIPHER_PART_MISSING')
                writer.write(chunk)
                writer.flush();os.fsync(writer.fileno())
            parts.append({'index':n,'name':part.name,'bytes':len(chunk),'sha256':sha(part)})
        if source.read(1):raise RuntimeError('HOLD_CIPHER_SIX_PART_OVERFLOW')
    if sum(x['bytes'] for x in parts)!=size:
        raise RuntimeError('HOLD_CIPHER_PART_SUM')
    index={
        'schema':'NOX_V70_SIX_CIPHER_PARTS_V1',
        'source_instance_id':60509551,
        'ciphertext_bytes':size,
        'ciphertext_sha256':sha(ENC),
        'parts':parts,
        'part_count':6,
        'owner_key_restore_verified':False,
        'user_pc_copy_verified':False,
        'vast_originals_deleted':False
    }
    INDEX.write_text(json.dumps(index,sort_keys=True,indent=2)+'\n')
    for item in parts:
        folder=PARTS_DIR/f"part{item['index']:02d}"
        (folder/INDEX.name).write_bytes(INDEX.read_bytes())
    return index


def run()->None:
    if not os.environ.get('NOX2'):
        raise RuntimeError('HOLD_VAST_API_SECRET_NOT_CONFIGURED')
    recipient,recipient_fingerprint=existing_owner_recipient_pinned()
    host,port=v60.live_direct_route()
    RUN.mkdir(mode=0o700,parents=True,exist_ok=True)
    test_key=RUN/'test_identity.agekey'
    subprocess.run(['age-keygen','-o',str(test_key)],
        check=True,timeout=12,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    test_key.chmod(0o600)
    test_pub=subprocess.run(['age-keygen','-y',str(test_key)],
        check=True,capture_output=True,text=True,timeout=12)
    if not test_pub.stdout.startswith('age1'):raise RuntimeError('HOLD_TEST_AGE_RECIPIENT')
    recipients=RUN/'recipients'
    recipients.write_text(recipient+'\n'+test_pub.stdout.strip()+'\n')
    recipients.chmod(0o600)
    v60.RUN=RUN
    known=RUN/'known_hosts'
    try:
        v60.attach_temporary_key()
        accepted=False
        for attempt in range(5):
            ENC.unlink(missing_ok=True)
            argv=['ssh','-T','-n','-i',str(v60.conn.KEY),'-p',str(port),
                '-o','BatchMode=yes','-o','IdentitiesOnly=yes',
                '-o','ConnectTimeout=12','-o','ServerAliveInterval=30','-o','ServerAliveCountMax=6','-o','StrictHostKeyChecking=accept-new',
                '-o','UserKnownHostsFile='+str(known),'root@'+host,
                'python3 -c '+shlex.quote(REMOTE)]
            remote=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            encrypted=subprocess.Popen(['age','-R',str(recipients),'-o',str(ENC)],
                stdin=remote.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            assert remote.stdout is not None
            remote.stdout.close()
            try:
                encrypted.communicate(timeout=1800)
                rc=remote.wait(timeout=30)
            except subprocess.TimeoutExpired:
                remote.kill();encrypted.kill()
                remote.communicate();encrypted.communicate()
                raise RuntimeError('HOLD_BATCH_STREAM_TIMEOUT')
            error=remote.stderr.read(12000) if remote.stderr else b''
            if rc==0 and encrypted.returncode==0 and ENC.exists() and ENC.stat().st_size>TOTAL:
                accepted=True;break
            if rc in (31,33,34,35):
                raise RuntimeError({31:'HOLD_COLD_FILE_COUNT_CHANGED',
                    33:'HOLD_COLD_FILE_CHANGED',
                    34:'HOLD_RAM_TMPFS_INSUFFICIENT',
                    35:'HOLD_COLD_FILE_OPEN_BY_SERVICE'}[rc])
            reason='AUTH' if b'permission denied' in error.lower() else (
                'NET' if rc==255 else 'STREAM')
            print('NOX_V70_STREAM_RETRY_CLASS='+reason)
            time.sleep(6)
        if not accepted:raise RuntimeError('HOLD_COLD_ONEPASS_STREAM')
        manifest=test_decrypt(ENC,test_key)
        index=split_ciphertext()
        record={
            'schema':'NOX_V70_COLD_ONEPASS_OFFSITE_RECEIPT_V1',
            'instance_id':60509551,
            'transferred_file_count':len(manifest),
            'source_total_bytes':sum(v['size_bytes'] for v in manifest),
            'ciphertext_bytes':index['ciphertext_bytes'],
            'ciphertext_sha256':index['ciphertext_sha256'],
            'ciphertext_parts_count':index['part_count'],
            'source_archive_manifest':manifest,
            'recipient_sha256':recipient_fingerprint,
            'temporary_test_key_restore_all_file_sha_verified':True,
            'owner_private_key_restoration_verified':False,
            'source_disk_files_deleted':False,
            'gpu_jobs_interrupted':False,
            'active_resonance_s03_main_model_untouched':True,
            'remote_ram_tmpfs_used_and_closed':True,
            'offsite_drive_uploaded':False,
            'user_pc_copy_verified':False
        }
        RECEIPT.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
        # First ciphertext chunk carries both indexes and the authenticated
        # source manifest for independent Drive/Windows acceptance.
        (PARTS_DIR/'part01'/RECEIPT.name).write_bytes(RECEIPT.read_bytes())
        print('NOX_V70_COLD_COUNT='+str(len(manifest)))
        print('NOX_V70_COLD_BYTES='+str(record['source_total_bytes']))
        print('NOX_V70_CIPHER_SHA256='+index['ciphertext_sha256'])
        print('NOX_V70_CIPHER_BYTES='+str(index['ciphertext_bytes']))
        print('NOX_V70_CIPHER_SIX_PARTS_VERIFIED=true')
        print('NOX_V70_INDEPENDENT_TEST_RESTORE_SHA=PASS_ALL')
    finally:
        try:
            if not v60.conn.cleanup():
                raise RuntimeError('HOLD_VAST_SSH_KEY_NOT_REVOKED')
            print('NOX_V70_VAST_SSH_KEY_REMOVED_AND_VERIFIED=true')
        finally:
            recipients.unlink(missing_ok=True)
            test_key.unlink(missing_ok=True)


if __name__=='__main__':
    try:run()
    except Exception as e:
        ENC.unlink(missing_ok=True)
        RECEIPT.unlink(missing_ok=True)
        msg=str(e)
        print(msg if msg.startswith('HOLD_') else 'HOLD_V70_ONEPASS_UNEXPECTED',file=sys.stderr)
        try:
            if v60.conn.TRACK.exists() and not v60.conn.cleanup():
                print('HOLD_V70_TEMP_SSH_CLEANUP',file=sys.stderr)
        except Exception:
            print('HOLD_V70_TEMP_SSH_CLEANUP',file=sys.stderr)
        raise SystemExit(2)
