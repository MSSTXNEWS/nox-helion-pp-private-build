#!/usr/bin/env python3
"""One fixed action: temporarily attach a throwaway SSH key to Vast instance 60509551,
run a fixed read-only telemetry command over SSH, then detach the key.
No remote downloads or raw training logs. Secret NOX2 is only sent to console.vast.ai."""
import json, os, re, subprocess, sys, tempfile, time, urllib.request, shutil
INSTANCE = 60509551
KEY = os.environ["NOX2"]
# A fixed, bounded read-only observer; no mutable network download or remote log tail.
# The reviewed commands ship with this Git commit, not with the current tip of main.
REMOTE = (
    "set -eu; "
    "for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; "
    "do if test -e \"$s\"; then printf 'STOP present\n'; fi; done; "
    "printf '== train\n'; "
    "train=$(supervisorctl status nox-train-qwen9b-t131u nox-train-keeper 2>/dev/null) || exit 41; printf '%s\n' \"$train\" | awk '{print $1, $2}'; "
    "printf '== gpu\n'; "
    "nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader; "
    "printf '== disk\n'; "
    "disk=$(df -h / 2>/dev/null) || exit 43; printf '%s\n' \"$disk\" | awk 'NR == 2 {print $4, $5}'; "
    "printf '== tasks\n'; "
    "python3 -c 'import json,collections; "
    "s=json.load(open(\"/root/nox/state/dispatcher/state.json\"))[\"tasks\"]; "
    "c=collections.Counter(t.get(\"status\") for t in s.values()); "
    "print(\" \".join(\"%s:%d\" % (k,c[k]) for k in (\"pending\",\"ready\",\"running\",\"done\",\"failed\",\"hold\")))'; "
    "printf '== svc\n'; "
    "services=$(supervisorctl status 2>/dev/null) || exit 44; printf '%s\n' \"$services\" | awk '$2 != \"RUNNING\" {print $1, $2}' | head -12"
)

def api(method, path, body=None):
    req = urllib.request.Request("https://console.vast.ai/api/v0" + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + KEY, "Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}

def main():
    inst = api("GET", "/instances/%d/" % INSTANCE)
    inst = inst.get("instances", inst)
    if isinstance(inst, list): inst = next(i for i in inst if i.get("id") == INSTANCE)
    ip = inst["public_ipaddr"]
    ports = [int(m["HostPort"]) for m in inst.get("ports", {}).get("22/tcp", []) if str(m.get("HostPort", "")).isdigit()]
    if inst.get("actual_status") != "running" or not ports: sys.exit("instance not running / no ssh port")
    d = tempfile.mkdtemp(prefix="nox-observer-"); kf = d + "/k"
    pub = None
    key_id = None
    attach_attempted = False
    try:
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "nox-update-button", "-f", kf], check=True)
        with open(kf + ".pub", encoding="utf-8") as handle:
            pub = handle.read().strip()
        attach_attempted = True  # A successful remote attach can outlive a failed API response.
        api("POST", "/instances/%d/ssh/" % INSTANCE, {"ssh_key": pub})
        for _ in range(8):
            rows = api("GET", "/instances/%d/ssh/" % INSTANCE)
            rows = rows if isinstance(rows, list) else rows.get("ssh_keys", rows.get("keys", []))
            hit = [r for r in rows if isinstance(r, dict) and pub.split()[1] in json.dumps(r)]
            if hit: key_id = hit[0].get("id"); break
            time.sleep(2)
        time.sleep(15)
        for port in ports:
            for attempt in range(3):
                r = subprocess.run(["ssh", "-T", "-i", kf, "-p", str(port), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
                    "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=" + d + "/kh",
                    "root@" + ip, REMOTE], capture_output=True, text=True, errors="replace", timeout=295, stdin=subprocess.DEVNULL)
                print("ssh rc=%d" % r.returncode); print(re.sub(r"(github_pat_\w+|tskey-[\w-]+)", "***", r.stdout[-3000:]))
                if r.returncode == 0: return
                time.sleep(10)
        sys.exit("ssh failed on all attempts")
    finally:
        cleanup_error = None
        try:
            # A delayed key-list update must not leave an attached temporary key
            # behind just because the first bounded lookup missed its ID.
            if attach_attempted and key_id is None:
                rows = api("GET", "/instances/%d/ssh/" % INSTANCE)
                rows = rows if isinstance(rows, list) else rows.get("ssh_keys", rows.get("keys", []))
                hits = [r for r in rows if isinstance(r, dict) and pub.split()[1] in json.dumps(r)]
                if hits:
                    key_id = hits[0].get("id")
            if key_id is not None:
                api("DELETE", "/instances/%d/ssh/%s" % (INSTANCE, key_id))
                print("temp key detached")
            elif attach_attempted:
                raise RuntimeError("HOLD_OBSERVER_EPHEMERAL_KEY_NOT_FOUND")
        except Exception as e:
            cleanup_error = e
            print("DETACH UNVERIFIED", type(e).__name__, "- remove 'nox-update-button' key in Vast manually")
        finally:
            # Delete private key and isolated known_hosts even if SSH/API failed.
            shutil.rmtree(d)
        if cleanup_error is not None:
            raise RuntimeError("HOLD_OBSERVER_KEY_DETACH_UNVERIFIED") from cleanup_error

if __name__ == "__main__":
    main()
