#!/usr/bin/env python3
"""Explicit owner-command transport; no push/PR activation or exported keys.
Separate from V51 read-only probe, reusing verified API and key-cleanup helpers.
"""
from __future__ import annotations
import argparse, base64, contextlib, ipaddress, json, os, re, socket, subprocess, sys, time
from pathlib import Path
REPO='MSSTXNEWS/nox-helion-pp-private-build'
OWNER_ID=340718567
INSTANCE=60509551
PIN='SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'
FILES={'audit':'nox-control/owner_native_audit.py','inspect':'nox-control/owner_native_inspect.py',
       'stage':'nox-control/owner_native_stage.py','repair':'nox-control/owner_native_repair.py'}

def authorize_event(action):
    e=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_EVENT_NAME')!='issue_comment':raise RuntimeError('HOLD_EVENT_SCOPE')
    c=e.get('comment',{});owner=e.get('repository',{}).get('owner',{})
    if (c.get('user',{}).get('id')!=OWNER_ID or owner.get('id')!=OWNER_ID or c.get('author_association')!='OWNER'
            or e.get('issue',{}).get('number')!=256 or e.get('sender',{}).get('id')!=OWNER_ID):raise RuntimeError('HOLD_OWNER_COMMAND_IDENTITY')
    sha=os.environ.get('NOX_PINNED_SOURCE_SHA','')
    if not re.fullmatch('[0-9a-f]{40}',sha):raise RuntimeError('HOLD_SOURCE_PIN')
    if c.get('body')!=f'/nox-maintain {INSTANCE} {sha} {action}':raise RuntimeError('HOLD_EXACT_OWNER_COMMAND')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise RuntimeError('HOLD_CHECKOUT_MISMATCH')
    return c['id']

def run_native(action,request_id):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
    key=os.environ.get('NOX2','')
    if not key:raise RuntimeError('HOLD_OWNER_API_CREDENTIAL_UNAVAILABLE')
    values=s.api('GET','/instances/',key)
    values=values.get('instances',values) if isinstance(values,dict) else values
    target=next((x for x in values if isinstance(x,dict) and str(x.get('id'))==str(INSTANCE)),None) if isinstance(values,list) else None
    if not target or target.get('actual_status')!='running' or str(target.get('num_gpus'))!='2':raise RuntimeError('HOLD_EXACT_RUNNING_INSTANCE')
    ip=target.get('public_ipaddr')
    if not ipaddress.ip_address(ip).is_global:raise RuntimeError('HOLD_INSTANCE_ROUTE')
    port=None
    for m in target.get('ports',{}).get('22/tcp',[]):
        value=str(m.get('HostPort',''))
        if not value.isdigit() or not 1<=int(value)<=65535:continue
        try:
            with socket.create_connection((ip,int(value)),timeout=6) as sock:
                sock.settimeout(5)
                if sock.recv(128).startswith(b'SSH-2.0'):port=int(value);break
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
    s.KEY.chmod(0o600);public=s.KEY.with_suffix('.pub').read_text().strip()
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
         '-o','ConnectTimeout=12','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','NumberOfPasswordPrompts=0',
         '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'root@'+ip]
    authed=False
    for _ in range(4):
        try:r=subprocess.run(cmd+['true'],capture_output=True,text=True,timeout=25)
        except subprocess.TimeoutExpired:continue
        if r.returncode==0:authed=True;break
        time.sleep(4)
    if not authed:raise RuntimeError('HOLD_SSH_AUTHENTICATION')
    print('NOX_MAINT_AUTHENTICATED_INSTANCE=60509551',flush=True)
    payload=Path(FILES[action]).read_text()
    if action in ('stage','repair'):
        assets={}
        for path in ('nox-control/nox_cold_drive.py','nox-control/owner_native_audit.py','nox-control/owner_native_inspect.py','nox-control/hybrid_training_entry.py'):
            p=Path(path)
            if p.is_file():assets[p.name]=base64.b64encode(p.read_bytes()).decode('ascii')
        payload=payload.replace('__NOX_BUNDLE_JSON__',json.dumps(assets))
    sha=os.environ['NOX_PINNED_SOURCE_SHA']
    script=f"set -euo pipefail\nNOX_OWNER_SOURCE_SHA={sha} NOX_OWNER_REQUEST_ID={int(request_id)} python3 - <<'NOX_OWNER_PAYLOAD'\n"+payload+"\nNOX_OWNER_PAYLOAD\n"
    # Execute ONCE after authenticated preflight. Never replay an uncertain mutation.
    timeout=120 if action in ('audit','inspect') else 900
    r=subprocess.run(cmd+['bash','-se'],input=script,capture_output=True,text=True,timeout=timeout)
    for line in r.stdout.splitlines():
        if line.startswith('NOX_MAINT_') and len(line)<180000:print(line,flush=True)
    print('NOX_MAINT_REMOTE_EXIT_CODE='+str(r.returncode),flush=True)
    marker='NOX_MAINT_'+action.upper()+'_COMPLETE=true'
    if r.returncode or marker not in r.stdout:raise RuntimeError('HOLD_NATIVE_PAYLOAD_INCOMPLETE')
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=FILES);args=p.parse_args();good=False
    try:
        request=authorize_event(args.action)
        print('NOX_MAINT_AUTHORIZED_COMMENT_ID='+str(request),flush=True)
        good=run_native(args.action,request)
    except Exception as e:
        code=str(e)
        print('NOX_MAINT_RESULT='+(code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else 'HOLD_'+type(e).__name__.upper()),flush=True)
    finally:
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as s
        try:
            if not s.cleanup():good=False
        except Exception:print('NOX_MAINT_CLEANUP=HOLD');good=False
        with contextlib.suppress(OSError):s.KEY.unlink()
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
