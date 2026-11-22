"""optlayer: боевая обвязка ядра NOX (c400). Три органа, все необязательные - сбой любого не роняет ход.

1. Телеметрия сервера: фоновый поток каждые 10 с снимает РЕАЛЬНЫЕ цифры (nvidia-smi, /proc/loadavg, /proc/meminfo, /proc/uptime,
   df, /health llama-серверов, статистика памяти :8095) -> блок для вопроса «как сервер?». Ничего не выдумывается: нет датчика - строки нет.
2. Семантический кэш (opt/semantic_cache.py, OPT-16): только вопросы мессира (intent=question), не eval, не время-зависимые;
   ключ контекста = sha(душа, блок памяти хода, модель) - сменилась память/душа -> старый ответ не подходит.
3. GLM-судья (opt/best_of_n_fast_judge.judge_pair) на :8081 как КЛИЕНТ (один префилл, 1 токен; llama-server не трогаем): на «explore»-попадании
   кэша сравнивает кэшированный и свежий ответ в обоих порядках A/B и отдаёт кэшу обратную связь (порог схожести растёт/падает).
   Занятый судья пропускается (чат важнее).
Флаги: NOX_OPT=0 выключает всё; NOX_OPT_CACHE=0, NOX_OPT_JUDGE=0, NOX_OPT_TELE=0 - по органам. NOX_JUDGE_URL (по умолчанию NOX_GLM_URL/:8081).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _d in (os.path.join(ROOT, "OPT"), os.path.join(ROOT, "opt")):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)

try:
    import semantic_cache as SC
except Exception:                      # opt не развёрнут
    SC = None
try:
    import best_of_n_fast_judge as BJ
except Exception:
    BJ = None


def _flag(name, default="1"):
    return os.environ.get(name, default).strip().lower() not in ("0", "off", "no", "false", "")


def _get(url, timeout=1.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "null")


def _sh(cmd, timeout=2.5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


# ---------------------------------------------------------------- телеметрия
def collect_telemetry(glm_url="http://127.0.0.1:8081", fast_url="http://127.0.0.1:8083", mem_api="http://127.0.0.1:8095"):
    """-> dict реальных замеров; отсутствующий датчик = нет ключа."""
    t = {"ts": time.time()}
    out = _sh(["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
               "--format=csv,noheader,nounits"])
    gpus = []
    for ln in out.strip().splitlines():
        p = [x.strip() for x in ln.split(",")]
        if len(p) >= 5:
            try:
                g = {"name": p[0], "util": float(p[1]), "mem_used_mib": float(p[2]), "mem_total_mib": float(p[3]), "temp_c": float(p[4])}
                if len(p) > 5:
                    try:
                        g["power_w"] = float(p[5])
                    except ValueError:
                        pass
                gpus.append(g)
            except ValueError:
                pass
    if gpus:
        t["gpus"] = gpus
    try:
        l1, l5, l15 = open("/proc/loadavg").read().split()[:3]
        t["load"] = [float(l1), float(l5), float(l15)]
        t["cpus"] = os.cpu_count()
    except Exception:
        pass
    try:
        mi = {}
        for ln in open("/proc/meminfo"):
            k, v = ln.split(":", 1)
            mi[k] = int(v.split()[0])
        t["ram_total_gb"] = round(mi["MemTotal"] / 1048576, 1)
        t["ram_avail_gb"] = round(mi["MemAvailable"] / 1048576, 1)
    except Exception:
        pass
    try:
        t["uptime_h"] = round(float(open("/proc/uptime").read().split()[0]) / 3600, 1)
    except Exception:
        pass
    try:
        st = os.statvfs("/root")
        t["disk_free_gb"] = round(st.f_bavail * st.f_frsize / 1e9, 0)
    except Exception:
        pass
    for key, url in (("glm", glm_url), ("fast", fast_url)):
        try:
            h = _get(url.rstrip("/") + "/health", 0.8)
            t[key] = "жива" if (h or {}).get("status") == "ok" else str(h)[:40]
            try:
                sl = _get(url.rstrip("/") + "/slots", 0.8)
                t[key + "_busy"] = sum(1 for s in sl if s.get("is_processing"))
            except Exception:
                pass
        except Exception:
            t[key] = "не отвечает"
    try:
        h = _get(mem_api.rstrip("/") + "/health", 0.8)
        t["memory"] = (h or {}).get("stats")
    except Exception:
        pass
    return t


def render_telemetry(t):
    if not t:
        return ""
    L = ["Реальные замеры сервера (на %s):" % time.strftime("%H:%M:%S", time.localtime(t.get("ts", time.time())))]
    for i, g in enumerate(t.get("gpus", [])):
        s = "GPU%d %s: загрузка %d%%, память %.1f из %.1f ГБ, %d°C" % (i, g["name"], g["util"], g["mem_used_mib"] / 1024, g["mem_total_mib"] / 1024, g["temp_c"])
        if "power_w" in g:
            s += ", %d Вт" % g["power_w"]
        L.append(s)
    if "load" in t:
        L.append("CPU: нагрузка %.2f / %.2f / %.2f (1/5/15 мин) на %s ядер" % (t["load"][0], t["load"][1], t["load"][2], t.get("cpus", "?")))
    if "ram_total_gb" in t:
        L.append("ОЗУ: свободно %.0f из %.0f ГБ" % (t["ram_avail_gb"], t["ram_total_gb"]))
    if "disk_free_gb" in t:
        L.append("Диск: свободно %d ГБ" % t["disk_free_gb"])
    if "uptime_h" in t:
        L.append("Аптайм: %.1f ч" % t["uptime_h"])
    for key, nm in (("glm", "Большая модель (GLM)"), ("fast", "Быстрая модель")):
        if key in t:
            L.append("%s: %s%s" % (nm, t[key], (", занятых слотов %d" % t[key + "_busy"]) if t.get(key + "_busy") is not None else ""))
    m = t.get("memory")
    if isinstance(m, dict):
        L.append("Память: фактов %s, эпизодов %s, записей профиля %s" % (m.get("facts"), m.get("episodes"), m.get("profile")))
    return "\n".join(L)


# ---------------------------------------------------------------- обвязка
class OptLayer:
    def __init__(self, state_dir=None, glm_url=None, fast_url=None):
        self.on = _flag("NOX_OPT")
        st = state_dir or os.environ.get("NOX_STATE", "/tmp")
        self.glm_url = glm_url or os.environ.get("NOX_GLM_URL", "http://127.0.0.1:8081")
        self.fast_url = fast_url or os.environ.get("NOX_FAST_URL", "http://127.0.0.1:8083")
        self.judge_url = os.environ.get("NOX_JUDGE_URL", self.glm_url)
        self.mem_api = os.environ.get("NOX_MEMORY_HEALTH", "http://127.0.0.1:8095")
        self.tele_on = self.on and _flag("NOX_OPT_TELE")
        self.judge_on = self.on and _flag("NOX_OPT_JUDGE") and BJ is not None
        self.cache = None
        self.stats = {"cache_hit": 0, "cache_explore": 0, "cache_put": 0, "cache_skip": 0, "judge_ok": 0, "judge_fail": 0, "judge_busy": 0, "tele": 0}
        if self.on and _flag("NOX_OPT_CACHE") and SC is not None:
            try:
                os.makedirs(st, exist_ok=True)
                self.cache = SC.SemanticCache(os.path.join(st, "semcache.db"), SC.HashEmbedder())
            except Exception:
                self.cache = None
        self._tele, self._lock, self._thr = None, threading.Lock(), None

    # --- телеметрия
    def start(self):
        if self.tele_on and self._thr is None:
            self._thr = threading.Thread(target=self._loop, daemon=True, name="nox-tele")
            self._thr.start()

    def _loop(self):
        while True:
            try:
                snap = collect_telemetry(self.glm_url, self.fast_url, self.mem_api)
                with self._lock:
                    self._tele = snap
                self.stats["tele"] += 1
            except Exception:
                pass
            time.sleep(10)

    def telemetry(self, fresh_s=60.0):
        with self._lock:
            t = self._tele
        if t is None or time.time() - t["ts"] > fresh_s:
            try:
                t = collect_telemetry(self.glm_url, self.fast_url, self.mem_api)
                with self._lock:
                    self._tele = t
            except Exception:
                t = None
        return t

    def telemetry_block(self, question):
        """Рамка для вопроса о сервере: реальные цифры + правило. Пусто, если замеров нет."""
        if not self.tele_on:
            return ""
        txt = render_telemetry(self.telemetry())
        if not txt:
            return ""
        return ("Вопрос мессира: %s\n\n<замеры_сервера>\n%s\n</замеры_сервера>\n\n"
                "Ответь мессиру коротко и по-человечески, назови только нужные цифры из замеров своими словами. "
                "Ничего не добавляй от себя: чего нет в замерах - того не знаешь." % (question, txt))

    # --- кэш
    @staticmethod
    def _skey(st, soul=""):
        m = getattr(st, "mem", None) or {}
        mem = str(m.get("core") or "")          # стабильное ядро памяти; всплывшие эпизоды меняются каждый ход и ключ не должны ломать
        return SC.make_ctx_key(hashlib.sha256((soul or "").encode()).hexdigest()[:16], hashlib.sha256(mem.encode()).hexdigest()[:16], "", "nox")

    def cacheable(self, st):
        return bool(self.cache) and st.intent == "question" and not st.opts.get("eval") and not st.opts.get("ablate") \
            and not st.council and not st.advice and st.speaker == "owner" and not st.opts.get("mode")

    def lookup(self, st, soul=""):
        """-> Hit|None. Hit.explore=True: вызывающий всё равно генерирует свежий ответ (для судьи)."""
        if not self.cacheable(st):
            return None
        try:
            h = self.cache.get(st.user_text, self._skey(st, soul))
        except Exception:
            return None
        if h is not None:
            self.stats["cache_explore" if h.explore else "cache_hit"] += 1
        return h

    def store(self, st, answer, soul=""):
        if not self.cacheable(st) or not answer:
            return None
        try:
            rid, why = self.cache.put(st.user_text, answer, self._skey(st, soul))
        except Exception:
            return None
        self.stats["cache_put" if rid else "cache_skip"] += 1
        return rid

    # --- судья
    def judge_sync(self, question, cached, fresh):
        """-> p(кэшированный не хуже) или None. Два префилла (A/B и B/A) на :8081; занят -> None."""
        if not self.judge_on:
            return None
        if BJ.judge_busy(self.judge_url):
            self.stats["judge_busy"] += 1
            return None
        p1, _ = BJ.judge_pair(self.judge_url, question, cached, fresh, 60)
        p2, _ = BJ.judge_pair(self.judge_url, question, fresh, cached, 60)
        if p1 is None or p2 is None:
            self.stats["judge_fail"] += 1
            return None
        self.stats["judge_ok"] += 1
        return (p1 + (1.0 - p2)) / 2.0

    def feedback(self, hit, ok):
        try:
            return self.cache.feedback(hit.entry_id, hit.sim, ok)
        except Exception:
            return False

    def status(self):
        d = dict(self.stats, on=self.on, cache=bool(self.cache), judge=self.judge_on, tele=self.tele_on, judge_url=self.judge_url)
        if self.cache:
            try:
                d["cache_stats"] = self.cache.stats()
            except Exception:
                pass
        return d


_OPT = None


def get():
    global _OPT
    if _OPT is None:
        _OPT = OptLayer()
        _OPT.start()
    return _OPT
