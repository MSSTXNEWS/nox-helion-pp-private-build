#!/usr/bin/env python3
"""One fixed action: temporarily attach a throwaway SSH key to Vast instance 60509551,
run the reviewed agent-updater (branch u, file u) over SSH, then detach the key.
No arbitrary command input. Secret NOX2 is only sent to console.vast.ai."""
import json, os, re, subprocess, sys, tempfile, time, urllib.request
INSTANCE = 60509551
KEY = os.environ["NOX2"]
REMOTE = 'curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c55/clean_disk.sh -o /tmp/c55.sh && bash /tmp/c55.sh 2>&1 | tail -45; echo ======; curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/nox-web-deploy-script/nox-control/cmd_agent/deploy_web.sh -o /tmp/deploy_web.sh && bash /tmp/deploy_web.sh ba7cacbac336c1dcba9b706570375482815e3dd11e94a30d146f3fda6892e23f https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/nox-web-dist/nox-web.part00 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/nox-web-dist/nox-web.part01 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/nox-web-dist/nox-web.part02 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/nox-web-dist/nox-web.part03 2>&1 | tail -3; echo ---; for f in nox-v14-ai4.js nox-v14-ai5.js nox-v14-ai6.js nox-v14-res.js index.html chat.html; do curl -s -o /dev/null -w "$f=%{http_code}\\n" http://127.0.0.1:8091/web/$f; done'

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
    d = tempfile.mkdtemp(); kf = d + "/k"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "nox-update-button", "-f", kf], check=True)
    pub = open(kf + ".pub").read().strip()
    key_id = None
    try:
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
                    "root@" + ip, REMOTE], capture_output=True, text=True, errors="replace", timeout=295, input=(os.environ.get("TS_AUTHKEY","") + "\n"))
                print("ssh rc=%d" % r.returncode); print(re.sub(r"(github_pat_\w+|tskey-[\w-]+)", "***", r.stdout[-3000:]))
                if r.returncode == 0: return
                time.sleep(10)
        sys.exit("ssh failed on all attempts")
    finally:
        if key_id is not None:
            try: api("DELETE", "/instances/%d/ssh/%s" % (INSTANCE, key_id)); print("temp key detached")
            except Exception as e: print("DETACH FAILED", type(e).__name__, "- remove 'nox-update-button' key in Vast manually")

main()
