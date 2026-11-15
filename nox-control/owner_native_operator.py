#!/usr/bin/env python3
"""Explicit owner-command native transport; no push/PR activation or exported keys.
Separate from V51 read-only probe. Reuses its verified API/key-cleanup helpers.
"""
from __future__ import annotations
import argparse, base64, contextlib, hashlib, ipaddress, json, os, re, signal, socket, subprocess, sys, time
from pathlib import Path

REPO='MSSTXNEWS/nox-helion-pp-private-build'
OWNER_ID=340718567
INSTANCE=60509551
PIN='SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'
FILES={'audit':'nox-control/owner_native_audit.py'}

def authorize_event(action):
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_EVENT_NAME')!='issue_comment':
        raise RuntimeError('HOLD_EVENT_SCOPE')
    comment=event.get('comment',{});owner=event.get('repository',{}).get('owner',{})
    if (comment.get('user',{}).get('id')!=OWNER_ID or owner.get('id')!=OWNER_ID
            or comment.get('author_association')!='OWNER' or event.get('issue',{}).get('number')!=256
            or event.get('sender',{}).get('id')!=OWNER_ID):
        raise RuntimeError('HOLD_OWNER_COMMAND_IDENTITY')
    sha=os.environ.get('NOX_PINNED_SOURCE_SHA','')
    if not re.fullmatch('[0-9a-f]{40}',sha):raise RuntimeError('HOLD_SOURCE_PIN')
    expected=f'/nox-maintain {INSTANCE} {sha} {action}'
    if comment.get('body')!=expected:raise RuntimeError('HOLD_EXACT_OWNER_COMMAND')
    actual=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if actual!=sha:raise RuntimeError('HOLD_CHECKOUT_MISMATCH')
    return comment['id']

def run_native(action):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
    key=os.environ.get('NOX2','')
    if not key:raise RuntimeError('HOLD_OWNER_API_CREDENTIAL_UNAVAILABLE')
    values=s.api('GET','/instances/',key)
    values=values.get('instances',values) if isinstance(values,dict) else values
    target=next((x for x in values if isinstance(x,dict) and str(x.get('id'))==str(INSTANCE)),None) if isinstance(values,list) else None
    if not target or target.get('actual_status')!='running' or str(target.get('num_gpus'))!='2':
        raise RuntimeError('HOLD_EXACT_RUNNING_INSTANCE')
    ip=target.get('public_ipaddr')
    if not ipaddress.ip_address(ip).is_global:raise RuntimeError('HOLD_INSTANCE_ROUTE')
    port=None
    for mapping in target.get('ports',{}).get('22/tcp',[]):
        candidate=str(mapping.get('HostPort',''))
        if not candidate.isdigit() or not 1<=int(candidate)<=65535:continue
        try:
            with socket.create_connection((ip,int(candidate)),timeout=6) as sock:
                sock.settimeout(5)
                if sock.recv(128).startswith(b'SSH-2.0'):port=int(candidate);break
        except OSError:continue
    if port is None:raise RuntimeError('HOLD_CURRENT_SSH_ROUTE')
    s.RUNNER.mkdir(parents=True,mode=0o700,exist_ok=True)
    known=s.RUNNER/'known_hosts'
    p=subprocess.run(['ssh-keyscan','-T','8','-t','ed25519','-p',str(port),ip],capture_output=True,text=True,timeout=12)
    known.write_text(p.stdout[:8000]);known.chmod(0o600)
    fp=subprocess.run(['ssh-keygen','-lf',str(known),'-E','sha256'],capture_output=True,text=True,timeout=8)
    if p.returncode or fp.returncode or PIN not in fp.stdout:raise RuntimeError('HOLD_OWNER_HOST_PIN')
    print('NOX_MAINT_HOST_PIN=VERIFIED',flush=True)
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-C','nox-owner-maint-'+os.environ.get('GITHUB_RUN_ID','manual'),'-f',str(s.KEY)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=12)
    s.KEY.chmod(0o600)
    public=s.KEY.with_suffix('.pub').read_text().strip()
    if not public.startswith('ssh-ed25519 ') or len(public)>700:raise RuntimeError('HOLD_PUBLIC_KEY_FORMAT')
    if s.match(key,public):raise RuntimeError('HOLD_KEY_COLLISION')
    s.TRACK.write_text(json.dumps({'public':public,'key_id':None}));s.TRACK.chmod(0o600)
    s.api('POST',f'/instances/{INSTANCE}/ssh/',key,{'ssh_key':public})
    ids=[]
    for _ in range(6):
        ids=s.match(key,public)
        if ids:break
        time.sleep(2)
    if len(ids)!=1:raise RuntimeError('HOLD_KEY_ATTACH_NOT_VERIFIED')
    s.TRACK.write_text(json.dumps({'public':public,'key_id':ids[0]}))
    cmd=['ssh','-T','-i',str(s.KEY),'-p',str(port),'-o','BatchMode=yes','-o','IdentitiesOnly=yes',
         '-o','ConnectTimeout=12','-o','NumberOfPasswordPrompts=0','-o','StrictHostKeyChecking=yes',
         '-o','UserKnownHostsFile='+str(known),'root@'+ip]
    authenticated=False
    for _ in range(4):
        r=subprocess.run(cmd+['true'],capture_output=True,text=True,timeout=25)
        if r.returncode==0:authenticated=True;break
        time.sleep(4)
    if not authenticated:raise RuntimeError('HOLD_SSH_AUTHENTICATION')
    print('NOX_MAINT_AUTHENTICATED_INSTANCE=60509551',flush=True)
    payload=Path(FILES[action]).read_bytes()
    # Only a fixed reviewed payload from the exact checkout, never issue text as code.
    script="set -euo pipefail\npython3 - <<'NOX_OWNER_PAYLOAD'\n"+payload.decode()+"\nNOX_OWNER_PAYLOAD\n"
    r=subprocess.run(cmd+['bash','-se'],input=script,capture_output=True,text=True,timeout=120)
    for line in r.stdout.splitlines():
        if line.startswith('NOX_MAINT_') and len(line)<150000:print(line,flush=True)
    print('NOX_MAINT_REMOTE_EXIT_CODE='+str(r.returncode),flush=True)
    if r.returncode or 'NOX_MAINT_AUDIT_COMPLETE=true' not in r.stdout:
        raise RuntimeError('HOLD_NATIVE_PAYLOAD_INCOMPLETE')
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=FILES);args=p.parse_args()
    good=False
    try:
        comment_id=authorize_event(args.action)
        print('NOX_MAINT_AUTHORIZED_COMMENT_ID='+str(comment_id),flush=True)
        good=run_native(args.action)
    except Exception as e:
        code=str(e)
        print('NOX_MAINT_RESULT='+(code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else 'HOLD_'+type(e).__name__.upper()),flush=True)
    finally:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
        try:
            if not s.cleanup():good=False
        except Exception:
            print('NOX_MAINT_CLEANUP=HOLD');good=False
        with contextlib.suppress(OSError):s.KEY.unlink()
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
