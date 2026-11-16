"""NOX V60: encrypted, streamed, restorable S03 + V29.3 snapshot.

No plaintext S03 is saved on GitHub runner or in its public artifacts.
Uses existing authorized Vast NOX2 to attach a temporary per-instance SSH key,
reads immutable per-file SQLite online snapshots into Vast tmpfs, streams a
tar.gz into age encryption on runner, and detaches the SSH key. The recipient
is an EXISTING owner SSH public key from Vast instance metadata, never an
ephemeral control key. A second temporary age recipient is used for in-run
decrypt / content-hash verification and discarded before artifact upload.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tarfile
import time

from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as conn
from nox_runpod.teacher_mesh.v60.restore_validator import verify_plaintext_tar

RUN = Path(os.environ.get("RUNNER_TEMP","/tmp")) / "nox-v60-critical"
FINAL = Path("NOX_V60_S03_GENESIS_WEB_20261114.tar.age")
RECEIPT = Path("NOX_V60_ENCRYPTED_BACKUP_RECEIPT.json")
REMOTE = r"""
import hashlib, io, json, os, sqlite3, sys, tarfile, tempfile
from pathlib import Path

root=Path('/root/nox')
dbs=[
 ('s03_seed_primary.sqlite3',root/'kb/pc_safe70/nox_seed_memory.sqlite3'),
 ('infinite_synaptic_memory.sqlite3',root/'memory/infinite/nox_infinite_memory.sqlite3'),
 ('s03_seed_second_copy.sqlite3',root/'memory/pc_t809u/nox_seed_memory.sqlite3'),
]
web_root=root/'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site'
web=[
 ('chat.html',web_root/'chat.html','b16aa117a9ff802529547693a92a5b97df9a8537a531dceb64e432b0c55901d3'),
 ('pc/resonance.html',web_root/'pc/resonance.html','9a5ee14787f4fc529926576339f86e07ce6ec838fe6e34fe6b2523f102719194'),
 ('nox-chat.js',web_root/'nox-chat.js','d9fa29e0fa726502adc6e83ea344adf13b8a2354acd3610b3de96ec378e942ce'),
 ('pc/nox-chat.js',web_root/'pc/nox-chat.js','7fcd4abf7f090ca66c54d90e432f4c4e433e887e0ba5ea0c89fe1acaf3a34238'),
]
if any(not p.is_file() or p.is_symlink() for _,p in dbs):
    raise SystemExit(17)
if any(not p.is_file() or p.is_symlink() for _,p,_ in web):
    raise SystemExit(18)
expected=sum(p.stat().st_size for _,p in dbs)
vfs=os.statvfs('/dev/shm')
free=vfs.f_bavail*vfs.f_frsize
if free < expected+20_000_000:raise SystemExit(19)
items=[]
with tempfile.TemporaryDirectory(prefix='nox_v60_',dir='/dev/shm') as scratch:
    source=[]
    for label,p in dbs:
        out=Path(scratch)/(label)
        # Online backup is consistent with SQLite WAL, without touching source.
        src=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=8)
        src.execute('PRAGMA query_only=ON')
        dst=sqlite3.connect(str(out))
        try:
            src.backup(dst,pages=512,sleep=0.02)
            answer=dst.execute('PRAGMA quick_check').fetchone()
            if answer is None or answer[0]!='ok':raise RuntimeError('SQLITE_SNAPSHOT_INVALID')
        finally:
            src.close();dst.close()
        source.append(('S03/'+label,out))
    for label,p,expected_sha in web:
        actual=hashlib.sha256(p.read_bytes()).hexdigest()
        if actual!=expected_sha:raise RuntimeError('WEB_SOURCE_LOCK_MISMATCH')
        source.append(('WEB_V29_3/site/'+label,p))
    for arc,p in source:
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
        items.append({'path':arc,'size_bytes':p.stat().st_size,'sha256':h.hexdigest()})
    meta={'schema':'NOX_V60_CRITICAL_BACKUP_MANIFEST_V1',
          'origin_instance_id':60509551,'snapshot':'SQLITE_ONLINE_BACKUP',
          's03_db_count':len(dbs),'web_lock_count':len(web),
          'source_contents_changed':False,'files':items}
    raw=json.dumps(meta,sort_keys=True,separators=(',',':')).encode()
    # Stream: remote stdout is the only plaintext output, age encrypts via pipe.
    with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
        for name,p in source:tar.add(p,arcname=name,recursive=False)
        ti=tarfile.TarInfo('RESTORE_MANIFEST.json')
        ti.size=len(raw);ti.mode=0o600;ti.mtime=0
        tar.addfile(ti,io.BytesIO(raw))
    sys.stdout.flush()
"""


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(2*1024*1024),b''):h.update(b)
    return h.hexdigest()


def existing_owner_recipient() -> tuple[str,str]:
    keys=conn.keys(os.environ["NOX2"])
    # This key was already present BEFORE we attach a temporary probe key.
    matching=[]
    for item in keys:
        k=str(item.get('public_key','')).strip()
        parts=k.split()
        if len(parts)>=2 and parts[0] in ('ssh-ed25519','ssh-rsa') and len(parts[1])<2500:
            matching.append(' '.join(parts[:2]))
    if len(matching)!=1:
        raise RuntimeError('HOLD_SINGLE_EXISTING_OWNER_SSH_RECIPIENT_REQUIRED')
    recipient=matching[0]
    fingerprint=hashlib.sha256(recipient.encode()).hexdigest()
    return recipient,fingerprint


def live_direct_route() -> tuple[str,int]:
    d=conn.api("GET",f"/instances/{conn.INSTANCE}/",os.environ["NOX2"])
    d=d.get('instances',d) if isinstance(d,dict) else None
    if isinstance(d,list):
        d=next((x for x in d if str(x.get('id'))==str(conn.INSTANCE)),None)
    if not isinstance(d,dict) or str(d.get('id'))!=str(conn.INSTANCE):
        raise RuntimeError('HOLD_VAST_INSTANCE_MISMATCH')
    if d.get('actual_status')!='running':
        raise RuntimeError('HOLD_NOT_RUNNING')
    host=d.get('public_ipaddr')
    import ipaddress
    try:
        if not ipaddress.ip_address(host).is_global:raise ValueError()
    except (TypeError,ValueError):
        raise RuntimeError('HOLD_NO_VERIFIED_PUBLIC_IP')
    mappings=d.get('ports') or {}
    for entry in mappings.get('22/tcp',[]):
        if not isinstance(entry,dict):continue
        value=entry.get('HostPort')
        if not str(value).isdigit() or not 1<=int(value)<=65535:continue
        try:
            with socket.create_connection((host,int(value)),timeout=5) as sock:
                sock.settimeout(4)
                if sock.recv(128).startswith(b'SSH-2.0'):
                    return host,int(value)
        except (OSError,TimeoutError):continue
    raise RuntimeError('HOLD_DIRECT_SSH_BANNER')


def attach_temporary_key() -> None:
    RUN.mkdir(mode=0o700,parents=True,exist_ok=True)
    conn.RUNNER=RUN
    conn.KEY=RUN/'ssh_identity'
    conn.TRACK=RUN/'cleanup.json'
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','',"-C","nox-v60-backup",
                    '-f',str(conn.KEY)],stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL,check=True,timeout=12)
    conn.KEY.chmod(0o600)
    public=conn.KEY.with_suffix('.pub').read_text().strip()
    if conn.match(os.environ['NOX2'],public):
        raise RuntimeError('HOLD_TEMP_SSH_KEY_COLLISION')
    conn.TRACK.write_text(json.dumps({'public':public,'key_id':None}))
    conn.TRACK.chmod(0o600)
    conn.api('POST',f'/instances/{conn.INSTANCE}/ssh/',os.environ['NOX2'],{'ssh_key':public})
    found=[]
    for _ in range(8):
        found=conn.match(os.environ['NOX2'],public)
        if found:break
        time.sleep(1.5)
    if len(found)!=1:
        raise RuntimeError('HOLD_TEMP_KEY_NOT_REGISTERED')
    conn.TRACK.write_text(json.dumps({'public':public,'key_id':found[0]}))
    print('NOX_V60_TEMP_KEY_ATTACH=VERIFIED')
    # Vast's running-container authorized_keys injection is not instantaneous:
    # earlier native probes authenticated only after several retries.
    time.sleep(12)


def restore_test(encrypted: Path, test_identity: Path) -> dict:
    p=subprocess.run(['age','-d','-i',str(test_identity),str(encrypted)],
                     capture_output=True,timeout=90)
    if p.returncode!=0:
        raise RuntimeError('HOLD_TEST_AGE_DECRYPTION')
    # Strict member coverage, path/type checks, pinned per-file SHA and SQLite
    # integrity run in-memory; no archive extraction or production DB writes.
    return verify_plaintext_tar(p.stdout)


def run() -> None:
    if not os.environ.get('NOX2'):
        raise RuntimeError('HOLD_NOX2')
    if not subprocess.run(['age','--version'],stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode==0:
        raise RuntimeError('HOLD_AGE_NOT_INSTALLED')
    owner,owner_hash=existing_owner_recipient()
    host,port=live_direct_route()
    RUN.mkdir(mode=0o700,parents=True,exist_ok=True)
    test_identity=RUN/'test_identity.agekey'
    gen=subprocess.run(['age-keygen','-o',str(test_identity)],stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,timeout=10)
    if gen.returncode:raise RuntimeError('HOLD_TEST_IDENTITY')
    test_identity.chmod(0o600)
    recipient=subprocess.run(['age-keygen','-y',str(test_identity)],capture_output=True,
                             text=True,timeout=10)
    if recipient.returncode or not recipient.stdout.startswith('age1'):
        raise RuntimeError('HOLD_TEST_RECIPIENT')
    recipients=RUN/'recipients'
    recipients.write_text(owner+'\n'+recipient.stdout.strip()+'\n')
    attach_temporary_key()
    known=RUN/'known_hosts'
    try:
        for attempt in range(10):
            FINAL.unlink(missing_ok=True)
            command=['ssh','-T','-i',str(conn.KEY),'-p',str(port),
                     '-o','BatchMode=yes','-o','IdentitiesOnly=yes',
                     '-o','ConnectTimeout=10',
                     '-o','StrictHostKeyChecking=accept-new',
                     '-o','UserKnownHostsFile='+str(known),
                     'root@'+host,'python3 -c '+shlex.quote(REMOTE)]
            ssh=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            crypt=subprocess.Popen(['age','-R',str(recipients),'-o',str(FINAL)],
                                   stdin=ssh.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            assert ssh.stdout is not None
            ssh.stdout.close()
            try:
                _,err=crypt.communicate(timeout=170)
                ssh_result=ssh.wait(timeout=12)
            except subprocess.TimeoutExpired:
                crypt.kill();ssh.kill()
                crypt.communicate();ssh.communicate()
                raise RuntimeError('HOLD_STREAM_TRANSFER_TIMEOUT')
            if ssh_result==0 and crypt.returncode==0 and FINAL.exists() and FINAL.stat().st_size>500:
                print('NOX_V60_STREAM_ENCRYPTED=PASS')
                break
            # Never log raw stdout/stderr: logs can contain host/route data.
            # Only fixed diagnostic classes, integer return codes and sizes.
            emsg=(ssh.stderr.read(12000) if ssh.stderr is not None else b'').lower()
            age_msg=(err or b'').lower()
            def matches(st,needles):
                return any(n in st for n in needles)
            if matches(emsg,(b'permission denied',b'authentication failed')):
                reason='SSH_AUTH'
            elif matches(emsg,(b'connection timed out',b'operation timed out')):
                reason='SSH_NETWORK_TIMEOUT'
            elif matches(emsg,(b'connection refused',b'connection reset')):
                reason='SSH_NETWORK_REFUSED_OR_RESET'
            elif matches(emsg,(b'traceback',b'sqlite3.',b'database is locked')):
                reason='REMOTE_PYTHON_OR_SQLITE'
            elif matches(age_msg,(b'no recipients',b'failed to parse',b'invalid recipient',b'unknown recipient')):
                reason='AGE_RECIPIENT'
            elif matches(age_msg,(b'failed to write',b'broken pipe')):
                reason='AGE_PIPE'
            else:
                reason='OTHER'
            print('NOX_V60_ATTEMPT_'+str(attempt+1)+'_CLASS='+reason)
            print('NOX_V60_ATTEMPT_'+str(attempt+1)+'_SSH_RC='+str(ssh_result))
            print('NOX_V60_ATTEMPT_'+str(attempt+1)+'_AGE_RC='+str(crypt.returncode))
            print('NOX_V60_ATTEMPT_'+str(attempt+1)+'_CIPHERTEXT_BYTES='+str(FINAL.stat().st_size if FINAL.exists() else 0))
            time.sleep(5)
        else:
            raise RuntimeError('HOLD_SSH_OR_AGE_STREAM')
        result=restore_test(FINAL,test_identity)
        out={
            'schema':'NOX_V60_OFFSITE_ENCRYPTED_BACKUP_RECEIPT_V1',
            'instance_id':60509551,
            'ciphertext_file':FINAL.name,
            'ciphertext_bytes':FINAL.stat().st_size,
            'ciphertext_sha256':sha256_file(FINAL),
            'existing_owner_ssh_recipient_sha256':owner_hash,
            'restoration_with_temporary_test_identity':'PASS',
            'restored_file_sha256_count':result['verified_files'],
            'plaintext_tar_sha256':result['restored_plain_sha256'],
            'web_frozen_source_count':4,
            'consistent_sqlite_online_backups':3,
            'raw_source_files_uploaded_to_github':False,
            'remote_source_files_deleted':False,
            'owner_ssh_private_key_decryption_tested':False,
            'native_queue_deployment':False,
        }
        RECEIPT.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
        print('NOX_V60_ENCRYPTED_BUNDLE_SHA256='+out['ciphertext_sha256'])
        print('NOX_V60_ENCRYPTED_BYTES='+str(out['ciphertext_bytes']))
        print('NOX_V60_DECRYPTED_ARCHIVE_HASHES_VERIFIED='+str(result['verified_files']))
        print('NOX_V60_SHA256_BACKUP_RECEIPT=PASS')
    finally:
        try:
            if not conn.cleanup():
                raise RuntimeError('HOLD_SSH_KEY_CLEANUP_NOT_VERIFIED')
            print('NOX_V60_TEMP_KEY_REMOVAL=DETACHED_AND_VERIFIED')
        finally:
            test_identity.unlink(missing_ok=True)
            recipients.unlink(missing_ok=True)


if __name__=="__main__":
    try:run()
    except Exception as exc:
        msg=str(exc)
        print(msg if msg.startswith("HOLD_") else "HOLD_V60_UNKNOWN",file=sys.stderr)
        try:
            if conn.TRACK.exists() and not conn.cleanup():
                print('HOLD_TEMP_KEY_CLEANUP',file=sys.stderr)
        except Exception:
            print('HOLD_TEMP_KEY_CLEANUP',file=sys.stderr)
        FINAL.unlink(missing_ok=True)
        raise SystemExit(2)
