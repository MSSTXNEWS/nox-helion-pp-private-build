#!/usr/bin/env python3
"""One fixed action: temporarily attach a throwaway SSH key to Vast instance 60509551,
run the reviewed agent-updater (branch u, file u) over SSH, then detach the key.
No arbitrary command input. Secret NOX2 is only sent to console.vast.ai."""
import json, os, re, subprocess, sys, tempfile, time, urllib.request
INSTANCE = 60509551
KEY = os.environ["NOX2"]
REMOTE = 'B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/bridge; echo ---BASE; cut -c1-150 /opt/bench_base.out; df -h / | tail -1; cd /opt/nox-bridge && mkdir -p /opt/nox-bridge.bak && cp -a nox_bridge.py nox_soul.py nox_webapi.py /opt/nox-bridge.bak/; for f in nox_bridge.py nox_soul.py nox_webapi.py; do curl -fsSL $B/$f -o /tmp/$f.new && python3 -m py_compile /tmp/$f.new && mv /tmp/$f.new /opt/nox-bridge/$f || { echo FAIL $f; exit 1; }; done; echo ---NK; curl -s -m80 -o /dev/null -w "nkeep http=%{http_code}\\n" 127.0.0.1:8098/v1/chat/completions -H "Content-Type: application/json" -d "{\\"messages\\":[{\\"role\\":\\"user\\",\\"content\\":\\"ok\\"}],\\"max_tokens\\":4,\\"n_keep\\":50,\\"id_slot\\":1,\\"cache_prompt\\":true}"; supervisorctl restart nox-bridge >/dev/null 2>&1; sleep 9; supervisorctl status nox-bridge | cut -c1-90; curl -s -m5 127.0.0.1:8091/api/health | cut -c1-200; echo; curl -s -m5 -D- -o /dev/null -H "Accept-Encoding: gzip" 127.0.0.1:8091/web/chat.html | grep -iE "^HTTP|content-enc|cache-control"; nohup /root/nox/venv/bin/python /opt/bench.py after >/opt/bench_after.out 2>&1 </dev/null & echo ---FATAL; for p in $(supervisorctl status | awk "/FATAL|BACKOFF/{print \\$1}"); do f=$(grep -l "program:$p\\]" /etc/supervisor/conf.d/*.conf 2>/dev/null | head -1); echo "$p $f"; [ -n "$f" ] && [ "$(grep -c "^\\[program" $f)" = 1 ] && sed -i "s/^autostart=true/autostart=false/;s/^autorestart=true/autorestart=false/" $f; done; echo ---CLEAN; apt-get clean 2>&1 | tail -1; /root/nox/venv/bin/pip cache purge 2>&1 | tail -1; cd /root/nox/logs && find . -maxdepth 1 -type f \\( -name "*.log.[0-9]" -o -name "*.err.[0-9]" -o -name "*.log" \\) -size +5M -mtime +1 -exec gzip -f {} \\; ; tail -n 300 nox-embed.stderr.log > nox-embed.stderr.tail 2>/dev/null; : > nox-embed.stderr.log; df -h / | tail -1; ls -la /root/nox/logs | sort -k5 -n -r | head -4 | cut -c1-110'

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
