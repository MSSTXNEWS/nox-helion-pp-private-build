#!/bin/bash
N=/workspace/nox
ss -ltn | grep -q ":18230 " && { echo "18230 busy"; pkill -f p3_status_svc.py; sleep 1; }
cat > $N/ops/p3_status_svc.py <<'PYEOF'
#!/usr/bin/env python3
"""P3 status service :18230 (stdlib, только чтение + свой append-only ledger). Эндпоинты для страницы system / UI:
 /train/status  строка статуса обучения + NO_GAIN   /hunger  шкала голода   /system/live  GPU, load, RAM, очереди   /ledger  хеш-цепочка (проверка)  /inspector  heartbeat инспектора
Часовой инспектор (поток): heartbeat state/p3/inspector_heartbeat.json, NO_GAIN -> запись в ledger. Откат: pkill -f p3_status_svc.py."""
import json, os, re, time, glob, hashlib, threading, subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
N = "/workspace/nox"; S = N + "/state/p3"; LEDGER = S + "/ledger.jsonl"; HB = S + "/inspector_heartbeat.json"; PORT = 18230
LOCK = threading.Lock()

def jl(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def sh(c, t=8):
    try: return subprocess.run(c, capture_output=True, timeout=t).stdout.decode("utf-8", "replace")
    except Exception: return ""

def last_log():
    fs = sorted(glob.glob(N + "/distill_v2/train_logs/train_*.log"), key=os.path.getmtime)
    return fs[-1] if fs else None

def train_status():
    f = last_log(); out = {"log": os.path.basename(f) if f else None, "ts": int(time.time())}
    if not f: return out
    lines = open(f, encoding="utf-8", errors="replace").read().splitlines()[-4000:]
    pts = []
    for l in lines:
        m = re.match(r"(\d\d):(\d\d):(\d\d) шаг (\d+), loss ([\d.]+), holdout CE ([\d.]+)", l)
        if m: pts.append((int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]), int(m[4]), float(m[5]), float(m[6])))
    ref = None
    for l in reversed(lines):
        m = re.search(r"опорного ([\d.]+) \(\+([\d.]+) допуск", l)
        if m: ref = float(m[1]); tol = float(m[2]); break
    steps_target = None
    cmd = sh(["pgrep", "-af", "distill_v2.py train"])
    m = re.search(r"--steps (\d+)", cmd); steps_target = int(m[1]) if m else None
    if pts:
        t, step, loss, ce = pts[-1]; out.update(step=step, loss=loss, holdout_ce=round(ce, 4), steps_target=steps_target)
        if len(pts) >= 2:
            dt = (pts[-1][0] - pts[-2][0]) % 86400; ds = pts[-1][1] - pts[-2][1]
            if ds > 0: out["s_per_step"] = round(dt / ds, 1); out["eta_min"] = round((steps_target - step) * dt / ds / 60) if steps_target else None
        ces = [p[3] for p in pts[-6:]]
        out["holdout_last"] = [round(c, 4) for c in ces]
        if ref: out["holdout_ref"] = ref; out["gain_vs_ref"] = round(ref - ce, 4)
        # NO_GAIN: последние >=5 оценок holdout улучшились меньше 0.003 относительно первой из них и опорного
        out["no_gain"] = bool(len(ces) >= 5 and (max(ces) - min(ces)) < 0.01 and (ref is None or ref - ces[-1] < 0.03))
        out["rollback_axis_drop"] = False   # >2 п.п. по оси: источник - gates/decision_*.json (см. /inspector)
    out["status_line"] = ("Обучение: шаг %s/%s, loss %s, holdout CE %s%s%s" % (out.get("step"), steps_target, out.get("loss"), out.get("holdout_ce"),
        (", %.1f с/шаг" % out["s_per_step"]) if out.get("s_per_step") else "", ", NO_GAIN" if out.get("no_gain") else "")) if pts else "Обучение: нет данных"
    sp = jl(N + "/state/speed.json", {}) or {}; out["ckpt_every"] = sp.get("ckpt_every")
    out["arbiter"] = (jl(N + "/state/arbiter.json", {}) or {}).get("mode")
    led = jl(N + "/state/core/genesis_ledger.json", {}) or {}
    b = [e for e in led.get("entries", []) if e.get("kind") == "birth"]
    out["born_at"] = b[0].get("iso") if b else None
    return out

def hunger():
    h = jl(N + "/state/worms_hb.json", {}) or {}; hh = h.get("hunger") or {}
    lvl = hh.get("level", 0); hours = hh.get("hours")
    return {"level": lvl, "hours": hours, "active_search": hh.get("active_search"), "scale_0_100": min(100, int((hours or 0) * 100 / 24)) if hours is not None else None, "ts": h.get("ts")}

def system_live():
    g = sh(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw", "--format=csv,noheader,nounits"]).strip().split(",")
    gpu = {}
    if len(g) >= 6: gpu = {"name": g[0].strip(), "mem_used_mb": int(g[1]), "mem_total_mb": int(g[2]), "util": int(g[3]), "temp": int(g[4]), "power_w": float(g[5])}
    la = open("/proc/loadavg").read().split()[:3]
    mi = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo") if ":" in l}
    q = 0
    try: q = sum(1 for _ in open(N + "/state/orch/bigjudge_queue.jsonl"))
    except Exception: pass
    slots = None
    try:
        import urllib.request
        sl = json.loads(urllib.request.urlopen("http://127.0.0.1:8104/slots", timeout=2).read()); slots = {"busy": sum(1 for s in sl if s.get("is_processing")), "n": len(sl)}
    except Exception: pass
    return {"gpu": gpu, "load": [float(x) for x in la], "ram_avail_gb": round(mi.get("MemAvailable", 0) / 1048576, 1), "ram_total_gb": round(mi.get("MemTotal", 0) / 1048576, 1),
            "queues": {"bigjudge": q}, "donor_slots": slots, "train": train_status().get("status_line"), "hunger": hunger()}

def ledger_append(kind, text):
    with LOCK:
        prev = "0" * 64; n = 0
        try:
            for l in open(LEDGER): r = json.loads(l); prev = r["h"]; n = r["n"] + 1
        except Exception: pass
        r = {"n": n, "ts": int(time.time()), "kind": kind, "text": text[:400], "prev": prev}
        r["h"] = hashlib.sha256((prev + json.dumps({k: r[k] for k in ("n", "ts", "kind", "text")}, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()
        with open(LEDGER, "a", encoding="utf-8") as f: f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return r

def ledger_check():
    prev = "0" * 64; n = 0; bad = None; tail = []
    try:
        for l in open(LEDGER):
            r = json.loads(l)
            h = hashlib.sha256((prev + json.dumps({k: r[k] for k in ("n", "ts", "kind", "text")}, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()
            if r["prev"] != prev or r["h"] != h: bad = r["n"]; break
            prev = r["h"]; n += 1; tail.append(r)
    except FileNotFoundError: pass
    return {"entries": n, "ok": bad is None, "broken_at": bad, "head": prev, "tail": tail[-5:]}

def inspector():
    last_flag = None
    while True:
        try:
            t = train_status(); notes = []
            if t.get("no_gain") and last_flag != t.get("step"):
                ledger_append("NO_GAIN", "holdout CE %s (ref %s) шаг %s: нет выигрыша за 5 оценок" % (t.get("holdout_ce"), t.get("holdout_ref"), t.get("step"))); last_flag = t.get("step"); notes.append("NO_GAIN")
            for p, nm in ((8104, "chat"), (8141, "mgr"), (8300, "judges"), (8793, "advisors")):
                ok = subprocess.run(["curl", "-s", "-m", "4", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:%d/health" % p], capture_output=True).stdout.decode()
                if ok not in ("200", "404"): notes.append("%s:%s" % (nm, ok))
            json.dump({"ts": int(time.time()), "ok": not notes or notes == ["NO_GAIN"], "notes": notes, "train": t.get("status_line")}, open(HB, "w"), ensure_ascii=False)
        except Exception as e:
            json.dump({"ts": int(time.time()), "ok": False, "error": str(e)[:120]}, open(HB, "w"))
        time.sleep(3600)

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        p = self.path.split("?")[0]
        m = {"/train/status": train_status, "/hunger": hunger, "/system/live": system_live, "/ledger": ledger_check, "/inspector": lambda: jl(HB, {"ok": None})}
        if p == "/health": b = {"ok": True}
        elif p in m:
            try: b = m[p]()
            except Exception as e: b = {"error": str(e)[:200]}
        else: self.send_response(404); self.end_headers(); return
        d = json.dumps(b, ensure_ascii=False).encode(); self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)

if __name__ == "__main__":
    os.makedirs(S, exist_ok=True)
    if not os.path.exists(LEDGER):
        led = jl(N + "/state/core/genesis_ledger.json", {}) or {}
        for e in led.get("entries", [])[:1]: ledger_append("birth", "born_at %s: %s" % (e.get("iso"), e.get("text")))
    threading.Thread(target=inspector, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
PYEOF
$N/venv/bin/python -m py_compile $N/ops/p3_status_svc.py && { nohup setsid $N/venv/bin/python $N/ops/p3_status_svc.py >> $N/state/p3/status_svc.log 2>&1 & }; sleep 4
for e in health train/status hunger system/live ledger inspector; do echo "== $e"; curl -s -m 20 127.0.0.1:18230/$e | head -c 700; echo; done
echo "== flux test2"; cat $N/state/p3/flux_test2.txt | cut -c1-400
echo "== decision json sample"; f=$(ls -t $N/distill_v2/gates/decision_*.json | head -1); python3 -c "
import json;d=json.load(open('$f'));print(json.dumps(d,ensure_ascii=False)[:1200])"
echo "== gateway cfg"; sed -n 1,12p $N/advisors/gateway.py | cut -c1-260; sed -n 60,82p $N/advisors/gateway.py | cut -c1-200
