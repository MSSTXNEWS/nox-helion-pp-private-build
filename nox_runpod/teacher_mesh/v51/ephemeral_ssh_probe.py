"""NOX V51: one-time temporary per-instance SSH access using EXISTING NOX2.

This does not create an SSH account key, API key, service, scheduler, or backend.
It uses Vast's documented per-instance POST /instances/<id>/ssh and cleans up
that exact temporary public key through DELETE /instances/<id>/ssh/<key_id>.
Run only in ephemeral GitHub Actions environment; never embed NOX2 in code.
"""
from __future__ import annotations
import json
import ipaddress
import socket
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

INSTANCE = 60509551
API = "https://console.vast.ai/api/v0"
RUNNER = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "nox-v51-ephemeral"
KEY = RUNNER / "identity"
TRACK = RUNNER / "cleanup.json"
HOST_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{1,253}$")

# Trust-boundary: data returned by the native command is heavily bounded,
# independently of what untrusted code might be present on the remote host.
REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,subprocess,re,json,shutil
def call(args,seconds=12):
    try:
        r=subprocess.run(args,capture_output=True,text=True,timeout=seconds)
        return r.returncode,r.stdout[:10000]
    except (OSError,subprocess.TimeoutExpired):
        return 99,''
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_CONTAINER_UID='+str(os.getuid()))
rc,out=call(['nvidia-smi','--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'])
if rc==0:
    rows=[v.strip() for v in out.splitlines() if v.strip() and len(v)<200][:4]
    print('NATIVE_GPU_QUERY=PASS')
    for row in rows:
        # No commands or untrusted process arguments are printed.
        if re.fullmatch(r'[\w, .+/-]{10,200}',row):
            print('NATIVE_GPU='+row)
else: print('NATIVE_GPU_QUERY=HOLD')
rc,out=call(['free','-b'])
if rc==0:
    for row in out.splitlines():
        if row.startswith('Mem:'):
            fields=row.split()
            if len(fields)>3:
                print('NATIVE_RAM_TOTAL_BYTES='+fields[1])
                print('NATIVE_RAM_USED_BYTES='+fields[2])
                break
rc,out=call(['df','-B1','/workspace'])
if rc==0:
    for line in out.splitlines()[1:2]:
        fields=line.split()
        if len(fields)>=4:
            print('NATIVE_WORKSPACE_DISK_TOTAL_BYTES='+fields[1])
            print('NATIVE_WORKSPACE_DISK_USED_BYTES='+fields[2])
            print('NATIVE_WORKSPACE_DISK_FREE_BYTES='+fields[3])
rc,out=call(['ps','-eo','comm='])
if rc==0:
    names=[x.strip().lower() for x in out.splitlines()]
    patterns={'python':'python','llama':'llama','ollama':'ollama','supervisor':'supervis','node':'node','jupyter':'jupyter'}
    for label,pattern in patterns.items():
        print('NATIVE_PROCESS_COUNT_'+label.upper()+'='+str(sum(pattern in name for name in names)))
rc,out=call(['supervisorctl','status'])
if rc==0:
    known=[]
    for row in out.splitlines()[:40]:
        fields=row.strip().split()
        if len(fields)>1 and re.fullmatch('[A-Za-z0-9_.:@-]{1,80}',fields[0]):
            known.append({'service':fields[0],'status':fields[1]})
    print('NATIVE_SUPERVISOR_STATUS='+json.dumps(known,sort_keys=True))
else: print('NATIVE_SUPERVISOR_STATUS=HOLD_NOT_AVAILABLE')
# Detect project artifacts by count only; never copy secrets, content or paths.
for label,root in [('workspace', '/workspace'),('nox_home', '/root')]:
    dirs=0
    if os.path.isdir(root):
        try:
            for item in os.scandir(root):
                if item.is_dir(follow_symlinks=False) and ('nox' in item.name.lower() or 'onehost' in item.name.lower()):
                    dirs+=1
        except OSError:pass
    print('NATIVE_NOX_TOPLEVEL_DIRS_'+label.upper()+'='+str(dirs))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""


def api(method: str, path: str, key: str, data: dict | None = None):
    if not key:
        raise RuntimeError("HOLD_NOX2_MISSING")
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    raw = None
    if data is not None:
        raw = json.dumps(data, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    url = ("https://console.vast.ai/api/v1" + path[3:]) if path.startswith("/v1/") else (API + path)
    request = urllib.request.Request(url, headers=headers, data=raw, method=method)
    try:
        with urllib.request.urlopen(request, timeout=22) as response:
            body = response.read(250000)
        value = json.loads(body)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HOLD_VAST_API_HTTP_" + str(exc.code)) from None
    if isinstance(value, dict) and value.get("success") is False:
        raise RuntimeError("HOLD_VAST_API_REJECTED_" + method)
    return value


def keys(key: str) -> list[dict]:
    data = api("GET", f"/instances/{INSTANCE}/ssh/", key)
    entries = data.get("ssh_keys", data.get("keys", [])) if isinstance(data, dict) else data
    if isinstance(entries, str):
        entries = json.loads(entries)
    if not isinstance(entries, list) or any(not isinstance(v, dict) for v in entries):
        raise RuntimeError("HOLD_VAST_INSTANCE_KEY_LIST")
    return entries


def match(key: str, public: str) -> list[int]:
    identity = public.strip().split()[:2]
    found = []
    for obj in keys(key):
        candidate = str(obj.get("public_key", obj.get("ssh_key", obj.get("key", ""))))
        if candidate.strip().split()[:2] == identity and len(identity) == 2:
            value = obj.get("id")
            if str(value).isdigit():
                found.append(int(value))
    return found


def cleanup() -> bool:
    key = os.environ.get("NOX2", "")
    if not TRACK.exists():
        print("TEMP_SSH_CLEANUP=NOT_ATTACHED")
        return True
    record = json.loads(TRACK.read_text())
    pub = record.get("public", "")
    if not pub.startswith("ssh-ed25519 "):
        print("TEMP_SSH_CLEANUP=HOLD_BAD_RECORD")
        return False
    ids = match(key, pub)
    # If attach was accepted and the key is missing already, cleanup succeeded.
    if not ids:
        print("TEMP_SSH_CLEANUP=ALREADY_ABSENT")
        TRACK.unlink(missing_ok=True)
        return True
    if len(ids) != 1:
        print("TEMP_SSH_CLEANUP=HOLD_AMBIGUOUS_KEY_ID")
        return False
    expected = record.get("key_id")
    if expected is not None and int(expected) != ids[0]:
        print("TEMP_SSH_CLEANUP=HOLD_KEY_ID_CHANGED")
        return False
    api("DELETE", f"/instances/{INSTANCE}/ssh/{ids[0]}/", key)
    for attempt in range(4):
        if not match(key, pub):
            print("TEMP_SSH_CLEANUP=DETACHED_AND_VERIFIED")
            TRACK.unlink(missing_ok=True)
            return True
        time.sleep(1.5)
    print("TEMP_SSH_CLEANUP=HOLD_STILL_ATTACHED")
    return False


def probe() -> bool:
    key = os.environ.get("NOX2", "")
    # Vast v0 instance routes can return 404 in new API deployments; v1 lists instances.
    d = api("GET", "/v1/instances/?owner=me&limit=25", key)
    d = d.get("instances", d) if isinstance(d, dict) else None
    if isinstance(d, list):
        d = next((row for row in d if str(row.get("id")) == str(INSTANCE)), None)
    if not isinstance(d, dict) or str(d.get("id")) != str(INSTANCE):
        raise RuntimeError("HOLD_WRONG_INSTANCE")
    if d.get("actual_status") != "running":
        raise RuntimeError("HOLD_INSTANCE_NOT_RUNNING")
    if str(d.get("num_gpus")) != "2":
        raise RuntimeError("HOLD_GPU_COUNT_CHANGED")
    # Vast proxy route sometimes accepts TCP but does not emit an SSH banner.
    # Prefer the direct, authenticated API-provided 22/tcp mapping, requiring
    # a genuine SSH-2.0 banner BEFORE generating or attaching any key.
    ip = d.get("public_ipaddr")
    try:
        if not ipaddress.ip_address(ip).is_global:
            raise ValueError("private")
    except (TypeError,ValueError):
        raise RuntimeError("HOLD_DIRECT_SSH_IP_NOT_GLOBAL")
    ports = d.get("ports")
    if not isinstance(ports,dict):
        raise RuntimeError("HOLD_DIRECT_SSH_PORT_MAP")
    mappings = ports.get("22/tcp")
    if not isinstance(mappings,list):
        raise RuntimeError("HOLD_DIRECT_SSH_MAPPINGS")
    host,port = None,None
    for row in mappings:
        if not isinstance(row,dict):
            continue
        raw = row.get("HostPort")
        if not str(raw).isdigit() or not (1<=int(raw)<=65535):
            continue
        try:
            with socket.create_connection((ip,int(raw)),timeout=7) as sock:
                sock.settimeout(5)
                banner = sock.recv(128)
                if banner.startswith(b"SSH-2.0"):
                    host,port = ip,int(raw)
                    break
        except (OSError,TimeoutError):
            continue
    if host is None:
        raise RuntimeError("HOLD_DIRECT_SSH_BANNER_UNAVAILABLE")
    print("SSH_ROUTE=VAST_API_DIRECT_MAPPED_22_WITH_BANNER")
    RUNNER.mkdir(mode=0o700,parents=True,exist_ok=True)
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C",
         "nox-v51-github-action-" + os.environ.get("GITHUB_RUN_ID", "ephemeral"),
         "-f", str(KEY)],stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,check=True,timeout=12)
    KEY.chmod(0o600)
    public = KEY.with_suffix(".pub").read_text().strip()
    if len(public) > 700 or not public.startswith("ssh-ed25519 "):
        raise RuntimeError("HOLD_EPHEMERAL_KEY_FORMAT")
    before_ids = set(match(key, public))
    if before_ids:
        raise RuntimeError("HOLD_EPHEMERAL_KEY_COLLISION")
    # Record BEFORE the attach attempt so cleanup can recover an uncertain POST.
    TRACK.write_text(json.dumps({"public": public, "key_id": None}))
    TRACK.chmod(0o600)
    api("POST", f"/instances/{INSTANCE}/ssh/", key, {"ssh_key": public})
    print("VAST_EPHEMERAL_PUBLIC_KEY_ATTACH_ACCEPTED=true")
    found = []
    for attempt in range(6):
        found = match(key, public)
        if found:
            break
        time.sleep(1.5)
    if len(found) != 1:
        raise RuntimeError("HOLD_EPHEMERAL_ATTACHED_KEY_ID_NOT_DISCOVERED")
    TRACK.write_text(json.dumps({"public":public,"key_id":found[0]}))
    print("VAST_EPHEMERAL_KEY_MATCHED_BY_EXACT_PUBLIC_KEY=true")
    print("VAST_INSTANCE_RUNNING_PRESERVED=true")
    known = RUNNER / "known_hosts"
    cmd = ["ssh","-vv","-T","-i",str(KEY),"-p",str(port),
           "-o","BatchMode=yes","-o","IdentitiesOnly=yes",
           "-o","ConnectTimeout=12","-o","NumberOfPasswordPrompts=0",
           "-o","StrictHostKeyChecking=accept-new",
           "-o","UserKnownHostsFile="+str(known),
           "root@"+host,"bash","-se"]
    for attempt in range(4):
        try:
            result = subprocess.run(cmd,input=REMOTE,encoding="utf-8",
                                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                    timeout=35)
        except subprocess.TimeoutExpired:
            print("SSH_ATTEMPT_"+str(attempt+1)+"=TIMEOUT")
            continue
        if result.returncode == 0 and "NATIVE_READ_ONLY_COMPLETE=true" in result.stdout and "NOX_NATIVE_V51_SSH_EXECUTED=true" in result.stdout:
            for line in result.stdout.splitlines():
                if len(line)<800 and line.startswith(("NOX_NATIVE_","NATIVE_")):
                    print(line)
            print("SSH_READONLY_REMOTE_EXIT_CODE=0")
            print("SSH_HOST_IDENTITY_POLICY=TOFU_EPHEMERAL_READ_ONLY")
            return True
        stderr = result.stderr.lower()
        checks = [
            ("permission denied", "AUTH_PERMISSION_DENIED"),
            ("host key verification failed", "HOST_KEY_VALIDATION"),
            ("connection refused", "NETWORK_REFUSED"),
            ("connection timed out", "NETWORK_TIMEOUT"),
            ("operation timed out", "NETWORK_TIMEOUT"),
            ("connection closed", "CONNECTION_CLOSED"),
            ("connection reset", "CONNECTION_RESET"),
            ("could not resolve hostname", "DNS_FAILURE"),
            ("kex_exchange_identification", "SSH_KEX_FAILURE"),
            ("no matching host key type", "HOST_KEY_ALGORITHM"),
            ("no route to host", "NETWORK_NO_ROUTE"),
            ("server accepts key", "KEY_ACCEPTED_REMOTE_FAILURE"),
        ]
        reason = next((name for needle,name in checks if needle in stderr),
                      "UNCLASSIFIED")
        print("SSH_ATTEMPT_"+str(attempt+1)+"=FAILED_RC_"+str(result.returncode))
        print("SSH_FAILURE_CLASS="+reason)
        time.sleep(4)
    raise RuntimeError("HOLD_EPHEMERAL_SSH_CONNECT_OR_EXECUTION")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if mode not in ("probe","cleanup"):
        raise SystemExit("HOLD_MODE")
    good = False
    if mode == "probe":
        try:
            good = probe()
        except Exception as exc:
            # Do not print exception text, which could include remote details.
            print("PROBE_RESULT="+str(exc) if str(exc).startswith("HOLD_") else "PROBE_RESULT=HOLD_NATIVE_PROBE_EXCEPTION")
        finally:
            try:
                if not cleanup():
                    good = False
            except Exception:
                print("TEMP_SSH_CLEANUP=HOLD_UNEXPECTED_FAILURE")
                good = False
    else:
        try:
            good = cleanup()
        except Exception:
            print("TEMP_SSH_CLEANUP=HOLD_UNEXPECTED_FAILURE")
    raise SystemExit(0 if good else 2)
