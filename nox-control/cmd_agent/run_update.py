#!/usr/bin/env python3
"""Read-only NOX owner observer. Never restart, deploy or print raw host logs."""
import json, os, re, shutil, subprocess, tempfile, time, urllib.request

INSTANCE=60509551
TOKEN=os.environ["NOX2"]
REMOTE="set -eu; printf 'NOX_OWNER_READONLY_V1\\n'; supervisorctl status nox-dispatcher-t855u nox-bridge 2>/dev/null | awk '{print $1, $2}'"
SERVICES={"nox-dispatcher-t855u", "nox-bridge"}

def api(method,path,body=None):
    req=urllib.request.Request("https://console.vast.ai/api/v0"+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization":"Bearer "+TOKEN,"Accept":"application/json",
                 "Content-Type":"application/json"},method=method)
    with urllib.request.urlopen(req,timeout=30) as r: data=r.read()
    return json.loads(data) if data else {}

def matching(pub):
    rows=api("GET","/instances/%d/ssh/"%INSTANCE)
    if isinstance(rows,dict): rows=rows.get("ssh_keys",rows.get("keys"))
    if not isinstance(rows,list): raise RuntimeError("HOLD_KEY_LIST_CONTRACT")
    identity=pub.split()[1]
    return [r for r in rows if isinstance(r,dict) and
            isinstance(r.get("ssh_key",r.get("key","")),str) and
            identity in r.get("ssh_key",r.get("key","")).split()]

def detach(pub):
    deleted=False
    for _ in range(5):
        for row in matching(pub):
            if row.get("id") is None: raise RuntimeError("HOLD_KEY_ID_MISSING")
            api("DELETE","/instances/%d/ssh/%s"%(INSTANCE,row["id"]))
            deleted=True
        if deleted:
            time.sleep(2)
            if not matching(pub):
                time.sleep(2)
                if not matching(pub): return True
        time.sleep(2)
    return False

def accepted(stdout):
    lines=stdout.splitlines()
    if not lines or lines[0].strip()!="NOX_OWNER_READONLY_V1": return False
    seen=set()
    for line in lines[1:]:
        m=re.fullmatch(r"([a-z0-9_-]+) (RUNNING|STOPPED|STARTING|BACKOFF|EXITED|FATAL)",line.strip())
        if m and m.group(1) in SERVICES and m.group(1) not in seen:
            seen.add(m.group(1))
            print(m.group(1)+"="+m.group(2))
    return seen==SERVICES

def main():
    inst=api("GET","/instances/%d/"%INSTANCE)
    inst=inst.get("instances",inst)
    if isinstance(inst,list): inst=next((x for x in inst if x.get("id")==INSTANCE),{})
    ports=[int(x["HostPort"]) for x in inst.get("ports",{}).get("22/tcp",[])
           if str(x.get("HostPort","")).isdigit()]
    if inst.get("actual_status")!="running" or not ports:
        raise RuntimeError("HOLD_INSTANCE_OR_PORT")
    directory=tempfile.mkdtemp(prefix="nox-owner-")
    keyfile=directory+"/key"
    pub=None; attached=False; removed=False
    try:
        subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-C",
                        "nox-owner-probe","-f",keyfile],check=True)
        with open(keyfile+".pub",encoding="utf-8") as f: pub=f.read().strip()
        attached=True
        api("POST","/instances/%d/ssh/"%INSTANCE,{"ssh_key":pub})
        confirmed=False
        for _ in range(8):
            if matching(pub): confirmed=True; break
            time.sleep(2)
        if not confirmed: raise RuntimeError("HOLD_KEY_ATTACH_UNCONFIRMED")
        time.sleep(10)
        for port in ports:
            r=subprocess.run(["ssh","-T","-i",keyfile,"-p",str(port),
                "-o","BatchMode=yes","-o","IdentitiesOnly=yes",
                "-o","ConnectTimeout=15","-o","StrictHostKeyChecking=accept-new",
                "-o","UserKnownHostsFile="+directory+"/known","root@"+inst["public_ipaddr"],REMOTE],
                capture_output=True,text=True,errors="replace",timeout=65,stdin=subprocess.DEVNULL)
            if r.returncode==0:
                if accepted(r.stdout):
                    print("owner_probe=READ_ONLY_VERIFIED")
                    return
                raise RuntimeError("HOLD_AMBIGUOUS_READBACK")
        raise RuntimeError("HOLD_SSH_FAILED")
    finally:
        try:
            if attached and pub: removed=detach(pub)
        finally:
            shutil.rmtree(directory,ignore_errors=True)
        if attached and not removed: raise RuntimeError("HOLD_KEY_DETACH_UNVERIFIED")

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("owner_probe=HOLD",type(exc).__name__)
        raise SystemExit(1)
