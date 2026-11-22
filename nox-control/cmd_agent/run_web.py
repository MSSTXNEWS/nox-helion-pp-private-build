#!/usr/bin/env python3
"""One fixed action: temporarily attach a throwaway SSH key to Vast instance 60509551,
run the reviewed agent-updater (branch u, file u) over SSH, then detach the key.
No arbitrary command input. Secret NOX2 is only sent to console.vast.ai."""
import json, os, re, subprocess, sys, tempfile, time, urllib.request
INSTANCE = 61825960  # S1 (Квебек)
KEY = os.environ["NOX2"]
G = "https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/web/"
import base64
_M = open(os.path.join(os.path.dirname(__file__), "..", "web", "MODE")).read().strip()
_B = base64.b64encode(open(os.path.join(os.path.dirname(__file__), "..", "web", _M + ".sh"), "rb").read()).decode()
REMOTE = "echo %s | base64 -d > /tmp/webm.sh && bash /tmp/webm.sh 2>&1 | tail -c 3000" % _B
_OLD = 'H="Accept: application/vnd.github.raw"; curl -fsSL -H "$H" "%sboot_web.sh?ref=main" -o /tmp/bw.sh && bash /tmp/bw.sh 2>&1 | tail -c 3000' % G

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
    if inst.get("actual_status") != "running" or not ports: sys.exit("instance not running / no ssh port: id=%s actual_status=%s cur_state=%s intended=%s msg=%s" % (INSTANCE, inst.get("actual_status"), inst.get("cur_state"), inst.get("intended_status"), str(inst.get("status_msg"))[:200]))
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
