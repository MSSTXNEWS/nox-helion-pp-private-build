# -*- coding: utf-8 -*-
"""nox_uptime: сквозной сторож доступности («NOX всегда на связи»). Программа supervisor nox_uptime.
Каждые 30 с проверяет цепочку: публичный адрес туннеля -> owner-gate :18092 -> Caddy :18091 -> /api/turn (короткий qa-ход, раз в 120 с или сразу после сбоя) -> :8104 /health -> сайдкар :18798 -> голос :18797.
В журнал state/uptime.log только коды и миллисекунды. Лечение по звену (не чаще 1 раза в 5 минут на звено, иначе алерт в state/alerts.jsonl):
 тело -> ops/body_safe_restart.sh (с --force, когда /health не отвечает); gate/caddy -> supervisorctl restart nox_web_chat_auth; сайдкар -> nox_sidecar; голос -> nox_voice;
 туннель -> перезапуск quick-tunnel cloudflared (--metrics 127.0.0.1:20999 --url http://127.0.0.1:18092); адрес берётся из /quicktunnel и пишется в state/core/public_url.json и строкой в утреннюю сводку (адрес без пароля, шифровать не нужно).
Лечится только корневое звено (нижнее в цепочке), «ход» сам не лечится. Во время перезапуска тела другими (замок body_restart/body_guard) не вмешивается.
Метрика: state/core/uptime_daily.json (по суткам UTC: samples, up, доля), weekly_exam пункт 1 читает chat_uptime_24h (цель >= 99.5%).
Выключатель: state/nox_uptime.off (только наблюдение без лечения: state/nox_uptime.noheal)."""
import os, sys, re, json, time, fcntl, threading, subprocess, urllib.request, http.client
N = os.environ.get("NOX_ROOT", "/workspace/nox"); ST = N + "/state"; S = ST + "/core"; M = ST + "/mind"
CF = "/opt/instance-tools/bin/cloudflared"; METRICS = "127.0.0.1:20999"; PERIOD = 30; TURN_EVERY = 4; HEAL_GAP = 300
ORDER = ["body", "sidecar", "voice", "caddy", "gate", "tunnel", "turn"]          # порядок лечения: сначала корень
NEED = {"body": 3, "sidecar": 2, "voice": 2, "caddy": 2, "gate": 2, "tunnel": 2, "turn": 99}   # подряд неудач до лечения
SUP = {"gate": "nox_web_chat_auth", "caddy": "nox_web_chat_auth", "sidecar": "nox_sidecar", "voice": "nox_voice"}
def now(): return time.time()
def http_code(url, timeout=5, method="GET", host_ok=None):
    t = time.time()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, method=method, headers={"User-Agent": "nox-uptime/1"}), timeout=timeout); c = r.status; r.read(256)
    except urllib.error.HTTPError as e: c = e.code
    except Exception: c = 0
    return c, int((time.time() - t) * 1000)
def quick_host():
    try: return json.loads(urllib.request.urlopen("http://%s/quicktunnel" % METRICS, timeout=3).read()).get("hostname")
    except Exception: return None
def chk_tunnel():
    h = quick_host()
    if not h: return (False, 0, 0, None)
    c, ms = http_code("https://%s/" % h, 10); return (c in (200, 301, 302, 401, 403), c, ms, h)   # 530/1033/502/0 = туннель мёртв
def chk_http(url, okset=None, below=500):
    c, ms = http_code(url, 5); return ((c in okset) if okset else (0 < c < below), c, ms)
def chk_body():
    t = time.time()
    try: b = urllib.request.urlopen("http://127.0.0.1:8104/health", timeout=4).read(); return (b'"ok"' in b, 200, int((time.time() - t) * 1000))
    except Exception: return (False, 0, int((time.time() - t) * 1000))
BUSY = re.compile(r"(?i)модель\s+занята|отвечаю\s+медленно|повтори\s+вопрос\s+через\s+минуту|не\s+сложился|сбой\s+черновика")
def chk_turn(timeout=45):
    t = time.time(); got = False; end = None; txt = ""
    try:
        c = http.client.HTTPConnection("127.0.0.1", 18091, timeout=timeout); body = json.dumps({"conversation_id": "qa-uptime", "message": "ответь одним словом: да", "mode": "fast", "user_id": "qa_exam"})
        c.request("POST", "/api/turn", body, {"Content-Type": "application/json"}); r = c.getresponse()
        if r.status != 200: return (False, r.status, int((time.time() - t) * 1000))
        while time.time() - t < timeout:
            ln = r.readline()
            if not ln: break
            try: o = json.loads(ln)
            except Exception: continue
            if o.get("t") == "delta": got = True; txt += str(o.get("text") or o.get("delta") or "")
            if o.get("t") in ("done", "error", "stopped"): end = o["t"]; break
        c.close()
    except Exception: return (False, 0, int((time.time() - t) * 1000))
    ok = (got or end == "done") and end != "error" and not BUSY.search(txt); return (ok, 200 if ok else 599, int((time.time() - t) * 1000))
def restart_in_progress():
    """Замки body_restart / body_guard заняты = кто-то уже перезапускает тело."""
    for p in (ST + "/body_restart.lock", ST + "/body_guard.lock"):
        try:
            f = open(p, "a"); fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(f.fileno(), fcntl.LOCK_UN); f.close()
        except OSError: return True
        except Exception: pass
    return os.path.exists(ST + "/gen_hold")
def sh(args, timeout=120):
    try: r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL); return r.returncode, (r.stdout or "")[-300:]
    except Exception as e: return 1, type(e).__name__
def jl(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d
def jw(p, o):
    try: os.makedirs(os.path.dirname(p), exist_ok=True); tmp = p + ".tmp"; open(tmp, "w", encoding="utf-8").write(json.dumps(o, ensure_ascii=False)); os.replace(tmp, p)
    except Exception: pass
class Watch:
    def __init__(self, checks=None, healers=None, clock=now, root=None):
        self.N = root or N; self.ST = self.N + "/state"; self.S = self.ST + "/core"; self.clock = clock
        self.checks = checks or {"tunnel": chk_tunnel, "gate": lambda: chk_http("http://127.0.0.1:18092/"), "caddy": lambda: chk_http("http://127.0.0.1:18091/"), "turn": chk_turn, "body": chk_body,
                                 "sidecar": lambda: chk_http("http://127.0.0.1:18798/health", {200}), "voice": lambda: chk_http("http://127.0.0.1:18797/")}
        self.healers = healers or {}; self.fails = {k: 0 for k in ORDER}; self.last_heal = {}; self.healing = set(); self.cycle = 0; self.last_turn = (True, 0, 0); self.alerted = {}; self.url = None
    def log(self, s):
        p = self.ST + "/uptime.log"
        try:
            if os.path.exists(p) and os.path.getsize(p) > 5_000_000: os.replace(p, p + ".1")
            open(p, "a").write("%s %s\n" % (time.strftime("%H:%M:%S", time.gmtime(self.clock())), s))
        except Exception: pass
    def alert(self, code, **kv):
        k = (code, kv.get("link"))
        if self.clock() - self.alerted.get(k, 0) < HEAL_GAP: return
        self.alerted[k] = self.clock()
        try: open(self.ST + "/alerts.jsonl", "a").write(json.dumps(dict(t=int(self.clock()), src="nox_uptime", code=code, **kv), ensure_ascii=False) + "\n")
        except Exception: pass
        self.log("ALERT %s %s" % (code, kv))
    def metric(self, up, down_links):
        p = self.S + "/uptime_daily.json"; d = jl(p, {"days": {}}); day = time.strftime("%F", time.gmtime(self.clock())); x = d["days"].setdefault(day, {"n": 0, "up": 0, "down_by": {}})
        x["n"] += 1; x["up"] += 1 if up else 0
        for l in down_links: x["down_by"][l] = x["down_by"].get(l, 0) + 1
        for k in sorted(d["days"])[:-14]: d["days"].pop(k, None)
        y = time.strftime("%F", time.gmtime(self.clock() - 86400)); n = x["n"] + d["days"].get(y, {}).get("n", 0); u = x["up"] + d["days"].get(y, {}).get("up", 0)
        d["chat_uptime_24h"] = round(u / n, 5) if n else None; d["samples_24h"] = n; d["t"] = int(self.clock()); d["target"] = 0.995; jw(p, d)
    def heal(self, link):
        if os.path.exists(self.ST + "/nox_uptime.noheal") or link in self.healing: return
        if self.clock() - self.last_heal.get(link, -1e9) < HEAL_GAP: self.alert("heal_limit", link=link, fails=self.fails[link]); return
        if link == "body" and restart_in_progress(): self.log("body: перезапуск уже идёт, жду"); return
        self.last_heal[link] = self.clock(); self.healing.add(link)
        def work():
            try:
                f = self.healers.get(link)
                if f: rc = f()
                elif link == "body": rc, _ = sh(["bash", self.N + "/ops/body_safe_restart.sh", "--force", "--reason", "nox_uptime: :8104 не отвечает"], 1000)
                elif link in SUP: rc, _ = sh(["supervisorctl", "restart", SUP[link]], 120)
                elif link == "tunnel": rc = self.heal_tunnel()
                else: rc = 0
                self.log("heal %s rc=%s" % (link, rc))
                if rc not in (0, None): self.alert("heal_failed", link=link, rc=rc)
            finally: self.healing.discard(link)
        t = threading.Thread(target=work, daemon=True); t.start(); return t
    def heal_tunnel(self):
        if quick_host():   # процесс жив, но адрес мёртв: пересоздаём
            sh(["bash", "-c", "pkill -f 'cloudflared tunnel .*--metrics %s' || true" % METRICS], 20); time.sleep(3)
        env = dict(os.environ, RUNNER_TRACKING_ID="")
        subprocess.Popen(["bash", "-c", "setsid nohup %s tunnel --no-autoupdate --metrics %s --url http://127.0.0.1:18092 >> %s 2>&1 < /dev/null &" % (CF, METRICS, self.ST + "/uptime_tunnel.log")], env=env, stdin=subprocess.DEVNULL)
        for _ in range(25):
            time.sleep(2)
            if quick_host(): self.sync_url(); return 0
        return 1
    def sync_url(self, host=None):
        host = host or quick_host()
        if not host: return
        u = "https://" + host; p = self.S + "/public_url.json"; d = jl(p, {}) or {}
        if d.get("url") != u:
            jw(p, {"url": u, "since": int(self.clock()), "prev": d.get("url"), "src": "cloudflared quick-tunnel -> :18092 (owner-gate), без пароля"}); self.alert("public_url_changed", link="tunnel"); self.brief(u)
        elif self.cycle % 20 == 0: self.brief(u)
        self.url = u
    def brief(self, u):
        for f in ("morning_brief_v5.json",):
            p = self.ST + "/mind/" + f; b = jl(p)
            if isinstance(b, dict):
                line = "Адрес чата: %s (вход по паролю)" % u
                if line not in (b.get("lines") or []) or b.get("public_url") != u:
                    b["lines"] = [x for x in (b.get("lines") or []) if not str(x).startswith("Адрес чата")] + [line]; b["public_url"] = u; jw(p, b)
    def step(self):
        self.cycle += 1; res = {}; 
        for k in ("tunnel", "gate", "caddy", "body", "sidecar", "voice"):
            try: r = self.checks[k]()
            except Exception: r = (False, 0, 0)
            res[k] = r
        if res["tunnel"][0] and len(res["tunnel"]) > 3 and res["tunnel"][3]: self.sync_url(res["tunnel"][3])
        base_ok = all(res[k][0] for k in ("tunnel", "gate", "caddy", "body"))
        if base_ok and (self.cycle % TURN_EVERY == 1 or not self.last_turn[0]):
            try: self.last_turn = self.checks["turn"]()
            except Exception: self.last_turn = (False, 0, 0)
        elif not base_ok: self.last_turn = (False, 0, 0)
        res["turn"] = self.last_turn
        for k in ORDER: self.fails[k] = 0 if res[k][0] else self.fails[k] + 1
        up = all(res[k][0] for k in ("tunnel", "gate", "caddy", "body", "turn")); down = [k for k in ORDER if not res[k][0]]
        self.log(" ".join("%s=%s/%d" % (k, res[k][1], res[k][2]) for k in ORDER) + " up=%d" % up); self.metric(up, down)
        for k in ORDER:
            if not res[k][0] and self.fails[k] >= NEED[k]:
                self.heal(k); break          # лечим только корневое звено
        if self.fails["turn"] >= 4: self.alert("turn_fail", link="turn", fails=self.fails["turn"])
        return res
def main():
    w = Watch()
    while True:
        t0 = time.time()
        try:
            if not os.path.exists(ST + "/nox_uptime.off"): w.step()
        except Exception as e: w.log("ошибка цикла %s" % type(e).__name__)
        time.sleep(max(1, PERIOD - (time.time() - t0)))
if __name__ == "__main__": main()
