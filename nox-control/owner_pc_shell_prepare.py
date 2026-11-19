#!/usr/bin/env python3
"""Prepare a dedicated SSH identity for the owner's voluntary PC reverse tunnel.

No PC connection is made here. The private key stays on the existing NOX host;
the Windows bootstrap retrieves only its public key over authenticated SSH.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

ROOT=Path('/root/nox')
STATE=ROOT/'state/pc_shell'
PORT=46051

def emit(data):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'pc_shell_preparation','data':data},separators=(',',':')),flush=True)

def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','')
    source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):raise RuntimeError('HOLD_OWNER_CONTEXT')
    if STATE.is_symlink():raise RuntimeError('HOLD_STATE_SYMLINK')
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(STATE,0o700)
    lock=os.open(STATE/'prepare.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        key=STATE/'operator_ed25519'
        public=Path(str(key)+'.pub')
        if key.is_symlink() or public.is_symlink():raise RuntimeError('HOLD_KEY_SYMLINK')
        if not key.exists():
            subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','NOX-owner-PC-shell-60509551','-f',str(key)],
                           check=True,capture_output=True,timeout=15)
        if not public.is_file():raise RuntimeError('HOLD_PUBLIC_KEY_MISSING')
        os.chmod(key,0o600);os.chmod(public,0o644)
        pub=public.read_text().strip()
        if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?',pub):raise RuntimeError('HOLD_PUBLIC_KEY_FORMAT')
        derived=subprocess.run(['ssh-keygen','-y','-f',str(key)],capture_output=True,text=True,timeout=8)
        if derived.returncode or derived.stdout.strip().split()[:2]!=pub.split()[:2]:raise RuntimeError('HOLD_KEY_PAIR_MISMATCH')
        r=subprocess.run(['/usr/sbin/sshd','-T'],capture_output=True,text=True,timeout=8)
        allowed={}
        for line in r.stdout.splitlines():
            fields=line.split(None,1)
            if len(fields)==2 and fields[0] in ('allowtcpforwarding','gatewayports','disableforwarding'):
                allowed[fields[0]]=fields[1]
        if r.returncode or allowed.get('allowtcpforwarding') not in ('yes','remote') or allowed.get('disableforwarding')=='yes':
            raise RuntimeError('HOLD_REVERSE_FORWARDING_NOT_AVAILABLE')
        if allowed.get('gatewayports') not in ('no','clientspecified'):
            raise RuntimeError('HOLD_REVERSE_FORWARDING_WOULD_EXPOSE_PUBLIC_LISTENER')
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',PORT));free=True
            except OSError:free=False
        if not free and not (STATE/'connection.json').is_file():raise RuntimeError('HOLD_REVERSE_PORT_ALREADY_OCCUPIED')
        result={'schema':'NOX_OWNER_PC_SHELL_V1','request':request,'source_sha':source,'prepared_at':time.time(),
                'state':'SERVER_READY_PC_BOOTSTRAP_REQUIRED','instance_id':60509551,
                'reverse_bind':'127.0.0.1','reverse_port':PORT,'port_available':free,
                'public_key_path':str(public),'public_key_sha256':hashlib.sha256(public.read_bytes()).hexdigest(),
                'private_key_exported':False,'sshd_forwarding':allowed,'pc_connected':False}
        receipt=STATE/('prepared_'+request+'.json')
        with receipt.open('x') as stream:json.dump(result,stream,indent=2)
        os.chmod(receipt,0o600);emit(result)
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    finally:os.close(lock)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        message=str(exc)
        emit({'state':'HOLD','error':message if re.fullmatch('HOLD_[A-Z_]+',message) else type(exc).__name__})
        raise SystemExit(2)
