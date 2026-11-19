"""One-shot Vast Docker SSH read-only audit using the existing NOX2 API secret.

An ephemeral SSH key is attached via the official API, never printed or saved
outside the runner; its exact ID is revoked in finally and verified via GET.
No restart, model change, service action, remote installation or general shell.
"""
from __future__ import annotations
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

INSTANCE = 60509551
BASE = "https://console.vast.ai/api/v0/"
PUBKEY = re.compile(r"^ssh-ed25519\s+[A-Za-z0-9+/=]+(?:\s+.*)?$")

REMOTE = r'''
import json,os,re,shutil,subprocess,sys
from pathlib import Path
nonce=sys.argv[1]
def run(args):
    try:
        p=subprocess.run(args,text=True,capture_output=True,timeout=12,check=False)
        return {"exit_code":p.returncode,"stdout":p.stdout[:15000]}
    except Exception as e:
        return {"exit_code":-1,"error_type":type(e).__name__}
gpu=run(["nvidia-smi","--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu","--format=csv,noheader,nounits"])
rows=[]
for line in gpu.get("stdout","").splitlines()[:4]:
    parts=[v.strip() for v in line.split(",")]
    if len(parts)==6:
        rows.append(dict(zip(["index","name","memory_total_mb","memory_used_mb","utilization_pct","temperature_c"],parts)))
disk=None
try:
    u=shutil.disk_usage("/workspace")
    disk={"total_bytes":u.total,"used_bytes":u.used,"free_bytes":u.free}
except OSError:pass
memory={}
try:
    for line in Path("/proc/meminfo").read_text().splitlines():
        key,_,value=line.partition(":")
        if key in ("MemTotal","MemAvailable","SwapTotal","SwapFree"):
            memory[key+"_kb"]=int(value.strip().split()[0])
except OSError:pass
processes=[]
try:
    for name in os.listdir("/proc"):
        if name.isdigit():
            try: comm=Path("/proc",name,"comm").read_text().strip()
            except (OSError,UnicodeError):continue
            if re.search(r"python|nox|ollama|llama|uvicorn|trainer|vllm",comm,re.I):
                processes.append({"pid":int(name),"comm":comm[:32]})
            if len(processes)>=35:break
except OSError:pass
workspace_entries=None
try:workspace_entries=min(1000,len(os.listdir("/workspace")))
except OSError:pass
label=os.getenv("VAST_CONTAINERLABEL","")
print(json.dumps({"schema":"NOX_V50_NATIVE_READ_AUDIT","nonce":nonce,
 "gpu_command_exit":gpu["exit_code"],"gpus":rows,
 "workspace_disk":disk,"meminfo":memory,"model_related_processes":processes,
 "workspace_entry_count":workspace_entries,
 "instance_label_matches":str(60509551) in label if label else None},separators=(",",":")))
'''


def public_key_identity(text: str) -> tuple[str, str] | None:
    if not isinstance(text, str) or not PUBKEY.fullmatch(text.strip()):
        return None
    values=text.strip().split()
    return (values[0],values[1])


def parse_ssh_keys(response: dict) -> list[dict]:
    value=response.get("ssh_keys")
    if isinstance(value,str):
        try:value=json.loads(value)
        except ValueError:raise RuntimeError("HOLD_KEY_LIST_JSON")
    if not isinstance(value,list) or any(not isinstance(v,dict) for v in value):
        raise RuntimeError("HOLD_KEY_LIST_SCHEMA")
    return value


def find_key_id(records: list[dict], public_key: str) -> int | None:
    identity=public_key_identity(public_key)
    if not identity:return None
    for record in records:
        value=record.get("public_key",record.get("ssh_key",record.get("key")))
        if public_key_identity(value)==identity:
            ident=record.get("id",record.get("ssh_key_id"))
            if type(ident) is int and ident>0:return ident
            if isinstance(ident,str) and ident.isdigit() and int(ident)>0:return int(ident)
    return None


def validated_route(instance: dict) -> tuple[str,int]:
    if str(instance.get("id"))!=str(INSTANCE) or instance.get("actual_status")!="running":
        raise RuntimeError("HOLD_INSTANCE_NOT_RUNNING")
    host=instance.get("ssh_host")
    port=instance.get("ssh_port")
    if not isinstance(host,str) or not host or not isinstance(port,(str,int)):
        raise RuntimeError("HOLD_NO_SSH_ROUTE")
    try:
        ip=ipaddress.ip_address(host)
        okay=ip.is_global
    except ValueError:
        okay=bool(re.fullmatch(r"(?:[a-z0-9-]+\.)*vast\.ai",host,re.I))
    if not okay or not str(port).isdigit() or not 1<=int(port)<=65535:
        raise RuntimeError("HOLD_SSH_ROUTE_INVALID")
    return host,int(port)


class Vast:
    def __init__(self,key:str):
        if not isinstance(key,str) or len(key)<10:
            raise RuntimeError("HOLD_NOX2_MISSING")
        self.key=key

    def api(self, path:str,method:str="GET",body:dict|None=None)->dict:
        if path=="instances/":
            # Documented GET /api/v0/instances/; never modify the list.
            if method!="GET" or body is not None:
                raise RuntimeError("HOLD_API_METHOD")
        else:
            if not re.fullmatch(r"instances/60509551/(?:ssh/(?:[0-9]+/?)?|)",path):
                raise RuntimeError("HOLD_API_PATH")
            instance_path=f"instances/{INSTANCE}/"
            keys_path=f"instances/{INSTANCE}/ssh/"
            if ((path==instance_path and method!="GET") or
                (path==keys_path and method not in ("GET","POST")) or
                (path not in (instance_path,keys_path) and
                 (not re.fullmatch(r"instances/60509551/ssh/[0-9]+/",path) or method!="DELETE"))):
                raise RuntimeError("HOLD_API_METHOD")
        headers={"Authorization":"Bearer "+self.key,
                 "Accept":"application/json"}
        raw=None
        if body is not None:
            if method!="POST" or set(body)!={"ssh_key"} or not public_key_identity(body["ssh_key"]):
                raise RuntimeError("HOLD_INVALID_ATTACH_BODY")
            raw=json.dumps(body,separators=(",",":")).encode()
            headers["Content-Type"]="application/json"
        req=urllib.request.Request(BASE+path,data=raw,headers=headers,method=method)
        try:
            with urllib.request.urlopen(req,timeout=25) as response:
                result=json.load(response)
        except urllib.error.HTTPError as e:
            raise RuntimeError("HOLD_VAST_HTTP_"+str(e.code)) from None
        if not isinstance(result,dict):
            raise RuntimeError("HOLD_VAST_RESPONSE")
        return result

    def instance(self):
        r=self.api("instances/")
        value=r.get("instances",r)
        if isinstance(value,list):
            value=next((v for v in value
                        if isinstance(v,dict) and str(v.get("id"))==str(INSTANCE)),None)
        if not isinstance(value,dict) or str(value.get("id"))!=str(INSTANCE):
            raise RuntimeError("HOLD_VAST_INSTANCE_SCHEMA")
        return value

    def keys(self):
        return parse_ssh_keys(self.api(f"instances/{INSTANCE}/ssh/"))

    def attach(self,public_key):
        r=self.api(f"instances/{INSTANCE}/ssh/","POST",{"ssh_key":public_key})
        if r.get("success") is not True:
            raise RuntimeError("HOLD_ATTACH_NOT_ACCEPTED")
        return r

    def detach(self,key_id):
        r=self.api(f"instances/{INSTANCE}/ssh/{key_id}/","DELETE")
        if r.get("success") is not True:
            raise RuntimeError("HOLD_DETACH_NOT_ACCEPTED")


def classify_ssh_error(stderr: str) -> str:
    """Never print raw SSH stderr (hostnames, routes and fingerprints are private)."""
    lower=stderr.lower()
    patterns=(
        ("remote host identification has changed","HOST_KEY_CHANGED"),
        ("host key verification failed","HOST_KEY_REJECTED"),
        ("permission denied","AUTH_DENIED"),
        ("too many authentication failures","AUTH_KEYS_EXHAUSTED"),
        ("could not resolve hostname","DNS_FAILURE"),
        ("connection refused","CONNECT_REFUSED"),
        ("connection timed out","CONNECT_TIMEOUT"),
        ("no route to host","NO_ROUTE"),
        ("connection reset","CONNECT_RESET"),
        ("connection closed","CONNECT_CLOSED"),
        ("kex_exchange_identification","KEY_EXCHANGE"),
        ("bad permissions","KEY_PERMISSIONS"),
        ("invalid format","KEY_FORMAT"),
        ("open failed","PROXY_CHANNEL_FAILURE"),
    )
    for term,label in patterns:
        if term in lower:return label
    return "UNKNOWN_SSH_ERROR"


def ssh_audit(host:str,port:int,private_key:Path,known_hosts:Path)->dict:
    nonce=secrets.token_hex(16)
    remote_command="python3 -c "+shlex.quote(REMOTE)+" "+shlex.quote(nonce)
    command=["ssh","-T","-n","-o","BatchMode=yes",
             "-o","PasswordAuthentication=no","-o","KbdInteractiveAuthentication=no",
             "-o","IdentitiesOnly=yes","-o","StrictHostKeyChecking=accept-new",
             "-o","UpdateHostKeys=no","-o","LogLevel=ERROR",
             "-o",f"UserKnownHostsFile={known_hosts}",
             "-o","ConnectTimeout=12","-i",str(private_key),
             "-p",str(port),"root@"+host,remote_command]
    for attempt in range(3):
        try:
            out=subprocess.run(command,capture_output=True,text=True,timeout=45,check=False)
        except subprocess.TimeoutExpired:
            return {"native_verified":False,"exit_code":124,"reason":"HOLD_SSH_TIMEOUT"}
        failure_class=classify_ssh_error(out.stderr)
        if out.returncode==255 and failure_class=="AUTH_DENIED" and attempt<2:
            # Vast's Docker agent may not apply newly attached keys instantly.
            # Bounded retry; never start a second process or touch trained weights.
            time.sleep(5+attempt*5)
            continue
        break
    result={"native_verified":False,"exit_code":out.returncode,
            "ssh_attempts":attempt+1,
            "ssh_error_class":failure_class if out.returncode else None,
            "stdout_sha256":hashlib.sha256(out.stdout.encode()).hexdigest(),
            "stderr_sha256":hashlib.sha256(out.stderr.encode()).hexdigest(),
            "stderr_present":bool(out.stderr)}
    if out.returncode!=0:
        result["reason"]="HOLD_SSH_EXIT_NONZERO"
        return result
    if len(out.stdout)>22000:
        result["reason"]="HOLD_SSH_OUTPUT_TOO_LARGE"
        return result
    try: data=json.loads(out.stdout)
    except (TypeError,ValueError):
        result["reason"]="HOLD_SSH_JSON"
        return result
    if not isinstance(data,dict) or data.get("schema")!="NOX_V50_NATIVE_READ_AUDIT" or data.get("nonce")!=nonce:
        result["reason"]="HOLD_SSH_NONCE_OR_SCHEMA"
        return result
    data.pop("nonce",None)
    result["native_verified"]=True
    result["resource_readback"]=data
    return result


def audit(vast:Vast)->dict:
    status={"schema":"NOX_V50_EPHEMERAL_SSH_AUDIT_V1","instance_id":INSTANCE,
            "api_verified":False,"native_verified":False,"ssh_key_detached_verified":False}
    public_key=None
    attached=False
    attempted_attach=False
    try:
        instance=vast.instance()
        host,port=validated_route(instance)
        vast.keys()  # Fail before any mutation if key-list API unavailable.
        status["api_verified"]=True
        with tempfile.TemporaryDirectory(prefix="nox-v50-ssh-") as folder:
            private_key=Path(folder)/"id_ed25519"
            subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","",
                            "-f",str(private_key)],
                           check=True,capture_output=True,timeout=12)
            public_key=(Path(str(private_key)+".pub").read_text()).strip()
            if not public_key_identity(public_key):
                raise RuntimeError("HOLD_GENERATED_PUBLIC_KEY")
            try:
                # Intentionally never print public key or provider SSH route.
                attempted_attach=True
                vast.attach(public_key)
                attached=True
                ids=[find_key_id(vast.keys(),public_key)]
                if ids[0] is None:
                    raise RuntimeError("HOLD_KEY_ID_NOT_REPORTED")
                status["remote"]=ssh_audit(host,port,private_key,Path(folder)/"known_hosts")
                status["native_verified"]=status["remote"]["native_verified"]
            finally:
                if attempted_attach:
                    try:
                        matching=find_key_id(vast.keys(),public_key)
                        if matching is None:
                            if attached:
                                raise RuntimeError("HOLD_KEY_NOT_FOUND_FOR_REVOKE")
                            # Attach failed; readback proves our exact key was not listed.
                            status["ssh_key_detached_verified"]=True
                        else:
                            vast.detach(matching)
                            remaining=find_key_id(vast.keys(),public_key)
                            status["ssh_key_detached_verified"]=remaining is None
                            if remaining is not None:status["cleanup_hold"]="HOLD_KEY_STILL_ATTACHED"
                    except Exception:
                        status["cleanup_hold"]="HOLD_REVOKE_NOT_VERIFIED"
    except Exception as e:
        message=str(e)
        status["reason"]=message if message.startswith("HOLD_") else "HOLD_AUDIT_EXCEPTION_"+type(e).__name__
    return status


def main():
    try:
        r=audit(Vast(os.getenv("VAST_API_KEY","")))
    except Exception:
        r={"schema":"NOX_V50_EPHEMERAL_SSH_AUDIT_V1","reason":"HOLD_PREFLIGHT_EXCEPTION"}
    # Only sanitized metrics; no IPs, keys, paths, raw stderr or env vars.
    print(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(",",":")))
    print("NOX_V50_REMOTE_ACCEPTED="+str(r.get("native_verified") is True).lower())
    print("NOX_V50_EPHEMERAL_KEY_REVOKED="+str(r.get("ssh_key_detached_verified") is True).lower())
    return 0 if r.get("native_verified") is True and r.get("ssh_key_detached_verified") is True else 2


if __name__=="__main__":
    raise SystemExit(main())
