"""One authenticated, no-retry native mutation over established Vast V51 route.

Not a daemon/second backend: run inside ephemeral GitHub Actions. Only trusted
checked-in local Python may supply the fixed remote program. SSH is authenticated
first with a harmless 'true'; the mutating script is sent EXACTLY ONCE. The
exact temporary key is revoked via existing V51 cleanup regardless of outcome.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as v51
import hashlib
import ipaddress
import json
import os
import re
import socket
import subprocess
import time

ID=60509551


def native_once(remote:str,required_marker:str="NATIVE_PATCH_COMPLETE=true")->dict:
    result={"schema":"NOX_V63_NATIVE_ONCE_V1","instance_id":ID,
            "native_ack":False,"remote_exit_code":None,
            "ssh_authenticated":False,"key_detached":False,
            "write_attempts":0}
    if required_marker!="NATIVE_PATCH_COMPLETE=true":
        return {**result,"state":"HOLD_ACK_PROTOCOL"}
    if not isinstance(remote,str) or len(remote)>45000:
        return {**result,"state":"HOLD_UNTRUSTED_REMOTE_SOURCE"}
    # The checked-in heredoc may start with one formatting newline; strip
    # only that newline, never permit a command prefix or arbitrary leading code.
    if remote.startswith("\n"):
        remote=remote[1:]
    if not remote.startswith("set -euo pipefail\npython3 - <<'PYREMOTE'\n"):
        return {**result,"state":"HOLD_UNTRUSTED_REMOTE_SOURCE"}
    secret=os.environ.get("NOX2","")
    if not isinstance(secret,str) or len(secret)<10:
        return {**result,"state":"HOLD_NOX2"}
    track_created=False
    try:
        if v51.TRACK.exists() or v51.KEY.exists():
            return {**result,"state":"HOLD_EPHEMERAL_COLLISION"}
        data=v51.api("GET",f"/instances/{ID}/",secret)
        d=data.get("instances",data) if isinstance(data,dict) else None
        if isinstance(d,list):
            d=next((x for x in d if str(x.get("id"))==str(ID)),None)
        if not isinstance(d,dict) or str(d.get("id"))!=str(ID) or d.get("actual_status")!="running":
            raise RuntimeError("HOLD_WRONG_INSTANCE")
        public_ip=d.get("public_ipaddr")
        try:
            if not ipaddress.ip_address(public_ip).is_global:raise ValueError()
        except (ValueError,TypeError):
            raise RuntimeError("HOLD_NON_PUBLIC_ROUTE")
        mappings=(d.get("ports") or {}).get("22/tcp")
        if not isinstance(mappings,list):
            raise RuntimeError("HOLD_NO_DIRECT_SSH_MAP")
        port=None
        for row in mappings:
            raw=row.get("HostPort") if isinstance(row,dict) else None
            if not str(raw).isdigit() or not 1<=int(raw)<=65535:continue
            try:
                with socket.create_connection((public_ip,int(raw)),timeout=6) as sock:
                    sock.settimeout(4)
                    banner=sock.recv(96)
                if banner.startswith(b"SSH-2.0"):
                    port=int(raw);break
            except (OSError,TimeoutError):pass
        if port is None:raise RuntimeError("HOLD_NO_SSH_BANNER")
        v51.RUNNER.mkdir(mode=0o700,parents=True,exist_ok=True)
        subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","",
                        "-C","nox-v63-once-"+os.environ.get("GITHUB_RUN_ID","ephemeral"),
                        "-f",str(v51.KEY)],capture_output=True,check=True,timeout=12)
        v51.KEY.chmod(0o600)
        public=v51.KEY.with_suffix(".pub").read_text().strip()
        if len(public)>700 or not public.startswith("ssh-ed25519 "):
            raise RuntimeError("HOLD_KEY_FORMAT")
        v51.TRACK.write_text(json.dumps({"public":public,"key_id":None}))
        v51.TRACK.chmod(0o600)
        track_created=True
        v51.api("POST",f"/instances/{ID}/ssh/",secret,{"ssh_key":public})
        found=[]
        for _ in range(7):
            found=v51.match(secret,public)
            if len(found)==1:break
            time.sleep(2)
        if len(found)!=1:raise RuntimeError("HOLD_ATTACHED_KEY_NOT_VERIFIED")
        v51.TRACK.write_text(json.dumps({"public":public,"key_id":found[0]}))
        time.sleep(18)
        common=["ssh","-T","-i",str(v51.KEY),"-p",str(port),
                "-o","BatchMode=yes","-o","IdentitiesOnly=yes",
                "-o","ConnectTimeout=12","-o","NumberOfPasswordPrompts=0",
                "-o","UserKnownHostsFile="+str(v51.RUNNER/"known_hosts")]
        target="root@"+public_ip
        for attempt in range(4):
            # Match the already proven V51 'bash -se' route, but run only
            # POSIX ':' (no-op). Do not transmit the patch until this succeeds.
            probe=subprocess.run(common+["-o","StrictHostKeyChecking=accept-new",target,"bash","-se"],
                                 input=":\n",capture_output=True,text=True,timeout=25)
            if probe.returncode==0:
                result["ssh_authenticated"]=True
                break
            error=probe.stderr.lower()
            reasons=(("permission denied","AUTH_DENIED"),
                     ("connection timed out","NETWORK_TIMEOUT"),
                     ("connection refused","NETWORK_REFUSED"),
                     ("host key verification failed","HOST_KEY_REJECTED"),
                     ("connection reset","NETWORK_RESET"),
                     ("connection closed","NETWORK_CLOSED"))
            result["ssh_auth_failure_class"]=next(
                (name for needle,name in reasons if needle in error),"OTHER_SSH_FAILURE")
            time.sleep(5)
        if not result["ssh_authenticated"]:
            raise RuntimeError("HOLD_SSH_AUTH_NOT_VERIFIED")
        # Once authenticated, require same pinned known_hosts for mutation.
        cmd=common
        result["write_attempts"]=1
        process=subprocess.run(cmd+["-o","StrictHostKeyChecking=yes",
                            target,"bash","-se"],input=remote,capture_output=True,
                            text=True,timeout=80)
        result["remote_exit_code"]=process.returncode
        result["stdout_sha256"]=hashlib.sha256(process.stdout.encode()).hexdigest()
        result["stderr_sha256"]=hashlib.sha256(process.stderr.encode()).hexdigest()
        # Only the deliberately bounded native receipt is ever returned.
        lines=[x for x in process.stdout.splitlines()
               if x.startswith("NATIVE_DOWNLOAD_PATH_REPAIR=") and len(x)<800]
        ack=required_marker in process.stdout.splitlines()
        result["native_ack"]=process.returncode==0 and ack and len(lines)==1
        if lines:
            try:
                receipt=json.loads(lines[0].split("=",1)[1])
                if isinstance(receipt,dict) and receipt.get("service")=="nox-downloads-t802u":
                    result["receipt"]=receipt
            except (TypeError,ValueError):pass
        result["state"]="NATIVE_RESULT_RECEIVED" if result["native_ack"] else "HOLD_NATIVE_WRITE_UNVERIFIED"
    except Exception as exc:
        msg=str(exc)
        result["state"]=msg if msg.startswith("HOLD_") and len(msg)<100 and re.fullmatch(r"[A-Z0-9_]+",msg) else "HOLD_NATIVE_ONCE_EXCEPTION"
    finally:
        # A failed attach may still have created the key; TRACK is saved
        # before POST, so the existing V51 cleanup reconciles that race.
        try:
            if track_created:
                result["key_detached"]=v51.cleanup() is True
            else:
                result["key_detached"]=not v51.TRACK.exists()
        except Exception:
            result["key_detached"]=False
        if not result["key_detached"]:
            result["cleanup_hold"]="HOLD_EXACT_KEY_REVOKE_UNVERIFIED"
    return result
