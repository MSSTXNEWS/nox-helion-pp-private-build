#!/usr/bin/env python3
"""NOX command agent: runs ONLY signed, allowlisted, non-destructive commands from the repo.
Pull: raw GitHub (anonymous). Push: comments on one issue (token with Issues:write only).
No arbitrary shell. Respects STOP files. Never touches model/weights/S03/services."""
import base64, json, os, shutil, subprocess, time, urllib.request, glob
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
REPO = "MSSTXNEWS/nox-helion-pp-private-build"
CMD_URL = "https://raw.githubusercontent.com/%s/nox-commands/commands/CMD.json" % REPO
PUB = base64.b64decode("bPL7Uky39TE9vTuko3T4/Xa/ffkrI0o4mawMR6Bw6ak=")
STATE = "/var/lib/nox/cmd_agent_state.json"
FLAG = "/var/lib/nox/autoclean.enabled"
TOKEN = os.environ.get("NOX_GH_TOKEN", "")
ISSUE = os.environ.get("NOX_RESULT_ISSUE", "")
STOPS = ["/root/nox/STOP", "/root/nox/STOP.flag", "/root/nox/state/STOP", "/root/nox/state/STOP.flag"]

def run(cmd, t=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return "ERR %s" % type(e).__name__

def meminfo():
    d = {}
    for l in open("/proc/meminfo"):
        k, v = l.split(":"); d[k] = int(v.split()[0]) // 1024
    return d

def cgroup_mem():
    out = {}
    for p in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current", "/sys/fs/cgroup/memory.high",
              "/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
        try: out[p.replace("/sys/fs/cgroup/", "")] = open(p).read().strip()
        except Exception: pass
    return out

def ram_status():
    m = meminfo()
    keys = ["MemTotal", "MemAvailable", "MemFree", "Cached", "Buffers", "SwapTotal", "SwapFree", "Shmem"]
    return json.dumps({"MB": {k: m.get(k) for k in keys}, "cgroup": cgroup_mem()}) + "\n" +         run(["bash", "-c", "ps -eo pid,rss,comm --sort=-rss | head -16"]) + "\n" +         run(["bash", "-c", "nvidia-smi --query-gpu=index,memory.used,memory.total,temperature.gpu --format=csv,noheader"]) + "\n" +         run(["df", "-h", "/", "/root"])

def clean_caches(force_drop=False):
    if any(os.path.exists(s) for s in STOPS): return "SKIPPED: STOP flag present"
    before = meminfo().get("MemAvailable")
    log = []
    for d in glob.glob("/root/.cache/pip/*") + glob.glob("/root/.cache/huggingface/xet/*tmp*"):
        shutil.rmtree(d, ignore_errors=True) if os.path.isdir(d) else None
    log.append(run(["apt-get", "clean"]))
    run(["sync"])
    if force_drop or before < 0.15 * meminfo().get("MemTotal", 1):
        try: open("/proc/sys/vm/drop_caches", "w").write("1"); log.append("drop_caches=1 OK")
        except Exception as e: log.append("drop_caches not permitted: %s" % type(e).__name__)
    after = meminfo().get("MemAvailable")
    return "MemAvailable MB: %s -> %s | %s" % (before, after, "; ".join(x for x in log if x))

def nox_status():
    out = []
    for port in (8080, 8098, 18775):
        out.append("port %d: %s" % (port, run(["bash", "-c", "curl -s -m 4 -o /dev/null -w '%%{http_code}' http://127.0.0.1:%d/ || echo down" % port])))
    out.append(run(["bash", "-c", "ps -eo pid,etimes,comm | grep -Ei 'nox|llama|python' | grep -v grep | head -20"]))
    return "\n".join(out)

def autoclean(args):
    os.makedirs("/var/lib/nox", exist_ok=True)
    if args.get("enabled"): open(FLAG, "w").write("1"); return "autoclean ENABLED (every 30 min, only if free RAM < 15%)"
    if os.path.exists(FLAG): os.remove(FLAG)
    return "autoclean DISABLED"

def disk_top(a):
    return run(["bash", "-c", "du -xh --max-depth=2 /root /workspace /var /opt 2>/dev/null | sort -rh | head -30"], 110)

def update(a):
    sha = str(a.get("sha", ""))
    if not (len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)): return "REFUSED: bad sha"
    url = "https://raw.githubusercontent.com/%s/%s/nox-control/cmd_agent/nox_cmd_agent.py" % (REPO, sha)
    code = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nox-cmd-agent"}), timeout=30).read()
    open("/opt/nox-cmd/agent.py.new", "wb").write(code)
    import py_compile; py_compile.compile("/opt/nox-cmd/agent.py.new", doraise=True)
    os.replace("/opt/nox-cmd/agent.py.new", "/opt/nox-cmd/agent.py")
    import threading; threading.Timer(3, lambda: os._exit(0)).start()
    return "updated to %s, restarting via supervisor" % sha[:7]

ACTIONS = {
    "disk_top": disk_top,
    "update": update,
    "ram_status": lambda a: ram_status(),
    "cache_clean": lambda a: clean_caches(bool(a.get("force_drop"))),
    "nox_status": lambda a: nox_status(),
    "autoclean": autoclean,
    "ping": lambda a: "pong " + time.strftime("%F %T"),
}

def verify(cmd):
    sig = base64.b64decode(cmd["sig"])
    body = json.dumps({k: v for k, v in cmd.items() if k != "sig"}, sort_keys=True, separators=(",", ":")).encode()
    Ed25519PublicKey.from_public_bytes(PUB).verify(sig, body)

def post(text):
    if not (TOKEN and ISSUE): print(text); return
    req = urllib.request.Request("https://api.github.com/repos/%s/issues/%s/comments" % (REPO, ISSUE),
        data=json.dumps({"body": text[:60000]}).encode(), method="POST",
        headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": "nox-cmd-agent"})
    try: urllib.request.urlopen(req, timeout=20)
    except Exception as e: print("post failed", type(e).__name__, getattr(e, "code", ""))

def load_state():
    try: return json.load(open(STATE))
    except Exception: return {"done": []}

def poll_once():
    st = load_state()
    try:
        cmd = json.load(urllib.request.urlopen(urllib.request.Request(CMD_URL + "?t=%d" % time.time(), headers={"User-Agent": "nox-cmd-agent"}), timeout=20))
        verify(cmd)
    except Exception as e:
        return
    if cmd["id"] in st["done"] or time.time() > cmd.get("not_after", 0): return
    act = cmd.get("action"); res = "REFUSED: action not allowed"
    if act in ACTIONS:
        try: res = ACTIONS[act](cmd.get("args", {}))
        except Exception as e: res = "ERR %s" % type(e).__name__
    st["done"] = (st["done"] + [cmd["id"]])[-200:]
    os.makedirs("/var/lib/nox", exist_ok=True); json.dump(st, open(STATE, "w"))
    post("**%s** `%s` @ %s\n```\n%s\n```" % (cmd["id"], act, time.strftime("%F %T"), res))

def main():
    last_clean = 0
    while True:
        poll_once()
        if os.path.exists(FLAG) and time.time() - last_clean > 1800:
            last_clean = time.time(); clean_caches(False)
        time.sleep(60)

if __name__ == "__main__":
    main()
