#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NOX CHAT V24 — локальный хост: Резонанс V22 (чёрное солнце D02 + поток NOX через Ollama). Основа — V21_1.

Только стандартная библиотека Python 3.12 (без pip).
  GET  /                      -> resonance.html (V22) + WEB V21 (web/)
  POST /api/nox/chat          -> SSE-поток ответа NOX (прокси к Ollama /api/chat, stream=true)
  POST /api/nox/stop          -> STOP: оборвать поток (request_id) — частичный ответ сохраняется со статусом stopped
  GET  /api/nox/history       -> список диалогов; ?dialog_id=... -> сообщения диалога (из SQLite)
  POST /api/nox/dialogs/new   -> новый диалог (старые не удаляются никогда)
  GET  /api/nox/memory        -> S03: счётчики M0–M7 и последние записи сегментов
  GET  /api/nox/progress      -> квитанция контракта %USERPROFILE%\\NOX\\progress\\nox-progress-receipt.json (иначе HOLD)
  GET  /api/nox/status        -> модель, Ollama, SAFE70
  GET  /api/pc-metrics        -> CPU/RAM/GPU (LibreHardwareMonitor WMI: °C, загрузка, VRAM), SAFE70
  GET  /api/nox/activity      -> active_generations (для реакции чёрного солнца nox-home.mjs)
  GET  /api/nox/birth         -> BIRTH_EVENT.json (pod1 birth.py), только чтение; рождение = квитанция VERIFIED
  GET/POST /api/settings      -> визуальные настройки workspace.js (MAX/BALANCED/ECO, motion, обращение)
Сообщения создателя пишутся в creator_messages (триггеры запрещают DELETE/UPDATE — канон).
"""
import os, sys, json, time, uuid, hashlib, sqlite3, threading, shutil, re, subprocess, urllib.request, urllib.error
import http.server, socketserver, mimetypes
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/epub+zip", ".epub")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("application/octet-stream", ".onnx")
from pathlib import Path

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
WEB = os.path.join(ROOT, "web")
HOME = os.environ.get("NOX_HOME") or os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"), "NOX")
MEMDIR = os.path.join(HOME, "memory")
DB_PATH = os.environ.get("NOX_DB") or os.path.join(MEMDIR, "nox_seed_memory.sqlite3")
PASSPORT_DIR = os.path.join(HOME, "passport")
RECEIPT = os.environ.get("NOX_RECEIPT") or os.path.join(HOME, "progress", "nox-progress-receipt.json")
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
PORT = int(os.environ.get("NOX_PORT", "8766"))
PRIMARY = os.environ.get("NOX_MODEL", "nox")  # единая модель nox или nox-prime; без выбора в интерфейсе
MODEL_MANIFEST = os.path.join(HOME, "models", "nox-prime.json")  # пишет nox_launch.py после проверки SHA256
SAFE70_LIMIT = float(os.environ.get("NOX_SAFE70_LIMIT", "70"))
SAFE70_RESUME = SAFE70_LIMIT - 5

# ---------- первый запуск: память и паспорт живут в %USERPROFILE%\NOX и не перезаписываются ----------
def _creator_count(path):
    try:
        c = sqlite3.connect(path); n = c.execute("select count(*) from creator_messages").fetchone()[0]; c.close(); return n
    except Exception:
        return -1

def bootstrap():
    os.makedirs(MEMDIR, exist_ok=True); os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    if not os.path.exists(PASSPORT_DIR):
        shutil.copytree(os.path.join(ROOT, "seed", "passport"), PASSPORT_DIR)
    if not os.path.exists(DB_PATH):
        # берём уже существующую память зародыша с ПК (больше всего сообщений создателя), иначе — из пакета
        up = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        cands = [os.path.join(ROOT, "seed", "memory", "nox_seed_memory.sqlite3")]
        for base in (os.path.join(up, "Downloads"), os.path.join(up, "Desktop"), os.path.join(up, "Documents"), up, "C:\\"):
            try:
                for d in os.listdir(base):
                    if d.upper().startswith("NOX"):
                        for sub in ("memory", os.path.join(d, "memory")):
                            p = os.path.join(base, d, "memory", "nox_seed_memory.sqlite3")
                            if os.path.exists(p) and p not in cands: cands.append(p)
            except Exception:
                pass
        # Reuse a real existing S03 database. Never silently create a second memory.
        existing = [p for p in cands if os.path.isfile(p) and _creator_count(p) >= 0]
        if existing:
            best = max(existing, key=_creator_count)
            shutil.copy2(best, DB_PATH)
            print("[NOX] существующая память перенесена из", best)
        elif os.environ.get("NOX_ALLOW_EMPTY_S03_BOOTSTRAP") == "1":
            # Explicit, clean FIRST INSTALL only. Existing databases are never modified.
            new_db = sqlite3.connect(DB_PATH)
            try:
                new_db.execute("PRAGMA user_version=0")
                new_db.commit()
            finally:
                new_db.close()
            print("[NOX] создана новая пустая S03 по явному разрешению; не restored backup")
        else:
            raise RuntimeError(
                "NOX_S03_EXISTING_DATABASE_MISSING_HOLD: no verified S03 seed or "
                "existing SQLite; set NOX_DB to the original file. "
                "Fresh empty memory requires NOX_ALLOW_EMPTY_S03_BOOTSTRAP=1")

bootstrap()
os.environ["NOX_DB"] = DB_PATH
os.environ.setdefault("NOX_MODEL", PRIMARY)
os.environ.setdefault("NOX_EMBED", "off")  # без сторонних моделей-эмбеддеров в Ollama-чате; индекс знаний — отдельно
sys.path.insert(0, MEMDIR)
try:
    import nox_knowledge as KN
except Exception:
    try:
        sys.path.insert(0, APP)
        import nox_knowledge as KN
    except Exception:
        KN = None
sys.path.insert(0, APP)
import nox_seed_live as LIVE          # переиспользуем: схема S03, retrieve(), remember(), now(), sha()
try:
    import nox_identity as IDENTITY
except Exception:
    IDENTITY = None
import nox_self_core as SC            # переиспользуем: SELF_CORE_v1 (M0–M7, ledger, самопроверка, рефлексия)
import nox_progress_core as PC        # контракт PR #241 (HOLD)
LIVE.PASSPORT = os.path.join(PASSPORT_DIR, "NOX_SEED_PASSPORT.json")
LIVE.PASSPORT_MD = os.path.join(PASSPORT_DIR, "PASSPORT.md")
now, sha = LIVE.now, LIVE.sha

CHAT_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_dialogs(id TEXT PRIMARY KEY, title TEXT, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS chat_dialogs_no_delete BEFORE DELETE ON chat_dialogs BEGIN SELECT RAISE(ABORT,'dialogs are permanent'); END;
CREATE TABLE IF NOT EXISTS chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, dialog_id TEXT NOT NULL, role TEXT NOT NULL,
  content TEXT NOT NULL, model TEXT, status TEXT NOT NULL, request_id TEXT, sha256 TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS chat_messages_no_delete BEFORE DELETE ON chat_messages BEGIN SELECT RAISE(ABORT,'chat history is permanent'); END;
CREATE TRIGGER IF NOT EXISTS chat_messages_no_update BEFORE UPDATE ON chat_messages BEGIN SELECT RAISE(ABORT,'chat history is append-only'); END;
CREATE INDEX IF NOT EXISTS chat_messages_dialog ON chat_messages(dialog_id, id);
CREATE TABLE IF NOT EXISTS chat_dialog_titles(id INTEGER PRIMARY KEY AUTOINCREMENT, dialog_id TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS chat_dialog_titles_no_delete BEFORE DELETE ON chat_dialog_titles BEGIN SELECT RAISE(ABORT,'titles are append-only'); END;
CREATE TRIGGER IF NOT EXISTS chat_dialog_titles_no_update BEFORE UPDATE ON chat_dialog_titles BEGIN SELECT RAISE(ABORT,'titles are append-only'); END;
"""
LOCK = threading.RLock()
CONN = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
CONN.execute("PRAGMA journal_mode=WAL")
CONN.executescript(LIVE.SCHEMA)
CONN.executescript(CHAT_SCHEMA)
CONN.commit()

import predator as PREDATOR
PREDATOR_HOST = None  # тик из safe70_loop; без локального GPU, кроме ответа в чате

try:
    import nox_helpers as HELPERS
    import nox_knowledge_tools as KTOOLS
    from nox_secrets import redact as _redact_secrets
except Exception:
    HELPERS = None
    KTOOLS = None
    def _redact_secrets(s, env=None):
        return str(s)[:300]
try:
    import nox_rag_fast as RAG_FAST
except Exception:
    RAG_FAST = None
try:
    import nox_soul as SOUL
except Exception:
    SOUL = None
try:
    import nox_ollama_speed as SPEED
    SPEED.apply_env()
except Exception:
    SPEED = None
try:
    import nox_voice as VOICE
except Exception:
    VOICE = None
try:
    import nox_self_tasks as SELF_TASKS
except Exception:
    SELF_TASKS = None
try:
    import nox_rates as RATES
except Exception:
    RATES = None
try:
    import nox_agents_loader as AGENTS
except Exception:
    AGENTS = None
try:
    from predator import surprise as SURPRISE
except Exception:
    SURPRISE = None

SESSION = time.strftime("%Y%m%d-%H%M%S") + "-v24-" + uuid.uuid4().hex[:6]
with LOCK:
    CORE = SC.SelfCore(CONN, LIVE.PASSPORT, model_name=PRIMARY, host=OLLAMA, session_id=SESSION, base_dir=HOME, now_fn=now)
    CONN.execute("insert into journal(session,kind,content,created_at) values(?,?,?,?)", (SESSION, "session_start", "NOX_CHAT_V24.1", now()))
    CONN.commit()

# ---------- Ollama ----------
def ollama_tags():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=4) as r:
            return json.loads(r.read().decode("utf-8")).get("models", [])
    except Exception:
        return None

def model_manifest():
    try:
        with open(MODEL_MANIFEST, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return None


def _model_names():
    primary = (os.environ.get("NOX_MODEL") or PRIMARY or "nox").strip() or "nox"
    names = []
    for n in (primary, primary + ":latest", "nox", "nox:latest", "nox-prime", "nox-prime:latest"):
        if n not in names:
            names.append(n)
    return names

def pick_model():
    """Один NOX: nox / nox:latest / nox-prime, проверенный манифестом, без выбора модели в UI."""
    tags = ollama_tags()
    if tags is None:
        return None, None, "OLLAMA_OFFLINE"
    by = {(m.get("name") or ""): m for m in tags}
    meta = None
    for n in _model_names():
        if n in by:
            meta = by[n]; break
        # some tags store "nox:latest"
        for k, m in by.items():
            if k == n or k.startswith(n.rstrip(":latest") + ":"):
                meta = m; break
        if meta:
            break
    if not meta:
        return None, None, "NOT_LOADED"
    man = model_manifest()
    det = meta.get("details") or {}
    digest_ok = bool(man and man.get("ollama_digest") and man.get("ollama_digest") == meta.get("digest"))
    sha_ok = bool(man and man.get("sha256") and len(str(man.get("sha256"))) == 64)
    pm = str(det.get("parent_model") or "")
    # Reject only a clearly different registry parent (qwen3:8b etc.). A FROM *.gguf build is NOX.
    if pm and not pm.lower().endswith(".gguf") and not digest_ok:
        return None, meta, "NOT_NOX"
    if man and man.get("ollama_digest") and man.get("ollama_digest") != meta.get("digest"):
        return None, meta, "UNVERIFIED_BUILD"
    if digest_ok or sha_ok or (meta.get("name") or "").split(":")[0] in ("nox", "nox-prime"):
        return meta.get("name"), meta, "NOX_PRIME"
    return None, meta, "UNVERIFIED_BUILD"

def _model_label(name, meta, kind):
    if kind == "OLLAMA_OFFLINE":
        return "NOX ещё не загружен: Ollama не отвечает (" + OLLAMA + ")"
    if kind == "NOT_LOADED":
        return "NOX ещё не загружен: положите файл полных весов в Загрузки или C:\\\\NOX\\\\models и запустите START_NOX.bat"
    if kind == "NOT_NOX":
        fam = ((meta or {}).get("details") or {}).get("family", "?")
        return "NOX ещё не загружен: в Ollama другая модель (семейство %s), нужен nox:latest" % fam
    if kind == "UNVERIFIED_BUILD":
        return "NOX ещё не загружен: digest nox в Ollama не совпал с проверенным файлом — START_NOX.bat --rebuild-model"
    man = model_manifest() or {}
    born = progress_receipt().get("nox_prime_born_at")
    step = man.get("step")
    quant = man.get("quant") or "Q4_K_M"
    tag = name or (meta or {}).get("name") or "nox"
    vb = verified_birth()
    if not born and vb.get("born_at"):
        lab = "NOX (%s, полные веса %s) — рождён %s %s · BIRTH_EVENT и SHA256 проверены" % (tag, quant, vb["born_at"][:10], vb["born_at"][11:19])
        if step not in (None, "", "None"):
            lab = lab.replace("NOX (", "NOX (шаг %s, " % step)
        return lab
    if born:
        extra = ("шаг %s, " % step) if step not in (None, "", "None") else ""
        return "NOX (%s, %sполные веса) — рождён %s" % (tag, extra, born)
    extra = ("шаг %s, " % step) if step not in (None, "", "None") else ""
    kind_w = (man.get("kind") or "")
    gg = str(man.get("file") or "").replace("\\", "/").lower()
    if kind_w in ("final_full", "merged_full") or "nox-final" in gg or (man.get("sha256") or "").lower().startswith("fee7cec8"):
        return "NOX (%s, %sполные финальные веса %s) — загружен, SHA256 %s… проверен" % (tag, extra, quant, (man.get("sha256") or "")[:8])
    return "NOX (%s, %sпромежуточные веса %s) — загружен, SHA256 проверен" % (tag, extra, quant)

def answer_source(kind):
    """Честная метка источника ответа. LIVE_NOX — только nox-prime из SHA-проверенного GGUF (манифест launcher'а)
    без пометки test_source. Тестовые стенды (mock Ollama, крошечная модель) обязаны писать test_source в манифест."""
    man = model_manifest() or {}
    t = str(man.get("test_source") or "").lower()
    if t:
        return ("MOCK", "ТЕСТ · mock Ollama — это НЕ ответ NOX") if "mock" in t else ("HARNESS", "ТЕСТ · модель-заглушка — это НЕ ответ NOX")
    if kind == "NOX_PRIME":
        return "LIVE_NOX", "ЖИВОЙ NOX · nox-prime GGUF · SHA256 проверен · Ollama"
    return "NONE", "NOX не подключён — ответов нет"

def model_label(name, meta, kind):
    src, lbl = answer_source(kind)
    base = _model_label(name, meta, kind)
    return (lbl + " · " + base) if src in ("MOCK", "HARNESS") else base

# ---------- SAFE70 ----------
SAFE = {"gpu_temp_c": None, "source": None, "paused": False, "limit": SAFE70_LIMIT, "checked_at": None, "note": "", "scope": "LOCAL_PC"}
SAFE.update({"decision": "HOLD", "reason": "", "streak_70": 0, "sensor": None, "gpu_hot_spot_c": None})
SAFE70_STATE = os.path.join(HOME, "progress", "safe70_state.json")

def _load_py_mod(name, *paths):
    import importlib.util
    for path in paths:
        if path and os.path.isfile(path):
            try:
                spec = importlib.util.spec_from_file_location(name, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod, path
            except Exception:
                continue
    return None, None

def _gpu_temp_mod():
    return _load_py_mod(
        "nox_gpu_temp",
        os.path.join(MEMDIR, "gpu_temp.py"),
        os.path.join(APP, "gpu_temp.py"),
    )

def _load_safe70_state():
    try:
        if os.path.isfile(SAFE70_STATE):
            with open(SAFE70_STATE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_safe70_state(state):
    try:
        os.makedirs(os.path.dirname(SAFE70_STATE), exist_ok=True)
        tmp = SAFE70_STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, SAFE70_STATE)
    except Exception:
        pass

# тот же метод V21 (LibreHardwareMonitor WMI); V22 дополнительно читает загрузку GPU Core и VRAM той же выборкой
PS_LHM = ("$n=@('root/LibreHardwareMonitor','root/OpenHardwareMonitor');foreach($x in $n){try{"
          "$a=Get-CimInstance -Namespace $x -ClassName Sensor -ErrorAction Stop|?{$_.Identifier -like '*gpu*' -or $_.Parent -like '*gpu*'};"
          "$s=$a|?{$_.SensorType -eq 'Temperature'};if($s){"
          "$l=($a|?{$_.SensorType -eq 'Load' -and $_.Name -eq 'GPU Core'}|Select-Object -First 1).Value;"
          "$u=($a|?{$_.SensorType -eq 'SmallData' -and $_.Name -eq 'GPU Memory Used'}|Select-Object -First 1).Value;"
          "$t=($a|?{$_.SensorType -eq 'SmallData' -and $_.Name -eq 'GPU Memory Total'}|Select-Object -First 1).Value;"
          "'{0}|{1}|{2}|{3}|{4}' -f (($s|Measure-Object Value -Maximum).Maximum),$x,$l,$u,$t;break}}catch{}}")
GPU_EXTRA = {"load": None, "vram_used_mb": None, "vram_total_mb": None, "source": None}
# запасной путь без LibreHardwareMonitor: счётчики Windows (WDDM, работают и для AMD Radeon) — загрузка 3D и выделенная VRAM; температуры там нет
PS_WDDM = ("$e=(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage' -ErrorAction Stop).CounterSamples|Measure-Object CookedValue -Sum;"
           "$m=(Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples|Measure-Object CookedValue -Maximum;"
           "$t=(Get-CimInstance Win32_VideoController|Measure-Object AdapterRAM -Maximum).Maximum;"
           "'{0}|{1}|{2}' -f [math]::Min(100,[math]::Round($e.Sum,1)),[math]::Round($m.Maximum/1MB),[math]::Round($t/1MB)")
def _num(v):
    try: return float(str(v).replace(",", "."))
    except Exception: return None

def read_gpu_temp():
    fake = os.environ.get("NOX_SAFE70_FAKE_TEMP_FILE")
    if fake and os.path.exists(fake):
        try: return float(open(fake).read().strip()), "TEST_FILE"
        except Exception: return None, None
    # Official reader: C:\\NOX\\memory\\gpu_temp.py (HTTP 8085 GPU Hot Spot), then packaged copy.
    mod, path = _gpu_temp_mod()
    if mod is not None:
        try:
            reading = mod.read_gpu_temp()
            t = reading.get("temp_c")
            if t is not None:
                SAFE["sensor"] = reading.get("sensor") or "GPU Hot Spot"
                SAFE["gpu_hot_spot_c"] = t
                return float(t), reading.get("source") or path
        except Exception:
            pass
    if os.name != "nt":
        return None, None
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", PS_LHM], capture_output=True, text=True, timeout=12,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        if "|" in out:
            parts = (out.split("|") + ["", "", ""])[:5]
            GPU_EXTRA["load"], GPU_EXTRA["vram_used_mb"], GPU_EXTRA["vram_total_mb"] = _num(parts[2]), _num(parts[3]), _num(parts[4])
            GPU_EXTRA["source"] = parts[1]
            return float(parts[0].replace(",", ".")), parts[1]
    except Exception:
        pass
    nv = shutil.which("nvidia-smi")  # на случай NVIDIA; у RX 6650M его нет
    if nv:
        try:
            o = subprocess.run([nv, "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip().splitlines()[0].split(",")
            GPU_EXTRA.update(load=_num(o[1]), vram_used_mb=_num(o[2]), vram_total_mb=_num(o[3]), source="nvidia-smi")
            return _num(o[0]), "nvidia-smi"
        except Exception: pass
    try:
        o = subprocess.run(["powershell", "-NoProfile", "-Command", PS_WDDM], capture_output=True, text=True, timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        if "|" in o:
            a = o.split("|"); GPU_EXTRA.update(load=_num(a[0]), vram_used_mb=_num(a[1]), vram_total_mb=_num(a[2]), source="Windows WDDM")
    except Exception: pass
    return None, None

def safe70_loop():
    while True:
        t, src = read_gpu_temp()
        SAFE["gpu_temp_c"], SAFE["source"], SAFE["checked_at"] = t, src, (IDENTITY.iso_moscow(now()) if IDENTITY else now())
        # SAFE70 = только ЛОКАЛЬНАЯ видеокарта ПК, на котором работает чат (LHM/nvidia-smi/WDDM этого ПК).
        # Облачные GPU (RunPod) и телеметрия обучения сюда не попадают и ECO фона не включают.
        SAFE["scope"] = "LOCAL_PC"
        decision, reason, streak = "HOLD", "sensor_missing_or_zero", 0
        mod, _path = _gpu_temp_mod()
        if mod is not None:
            try:
                decision, state, reason = mod.safe70_decide(t, _load_safe70_state())
                _save_safe70_state(state)
                streak = int(state.get("streak_70") or 0)
            except Exception as e:
                decision, reason = ("HOLD" if t is None else "OK"), "decide_error"
        else:
            if t is None:
                decision, reason = "HOLD", "sensor_missing_or_zero"
            elif t >= SAFE70_LIMIT:
                decision, reason = "STOP", "legacy_limit"
            elif t >= 65:
                decision, reason = "WARN", "legacy_warn"
            else:
                decision, reason = "OK", "legacy_ok"
        SAFE["decision"], SAFE["reason"], SAFE["streak_70"] = decision, reason, streak
        SAFE["gpu_hot_spot_c"] = t
        if decision == "STOP":
            if not SAFE["paused"]:
                for run in list(RUNS.values()):
                    run["stop"] = "SAFE70"
            SAFE["paused"] = True
        else:
            SAFE["paused"] = False  # WARN/OK/HOLD: чат доступен
        if t is None:
            SAFE["note"] = "SAFE70: HOLD — температура GPU не читается (" + str(reason) + ")"
        else:
            SAFE["note"] = (f"SAFE70 {decision}: GPU Hot Spot {t:.0f}°C"
                            + (f" · серия {streak}" if streak else "")
                            + (f" — генерация на паузе ({reason})" if decision == "STOP" else f" ({reason})"))
        try:
            if PREDATOR_HOST is not None:
                PREDATOR_HOST.tick()
        except Exception:
            pass
        time.sleep(float(os.environ.get("NOX_SAFE70_INTERVAL", "5")))

# ---------- метрики ПК ----------
_cpu_prev = None
def pc_metrics():
    global _cpu_prev
    m = {"source": "NOX_CHAT_V24 local host", "timestamp": time.time(), "cpu_source": "OS", "ram_source": "OS"}
    try:
        if os.name == "nt":
            import ctypes
            class FT(ctypes.Structure): _fields_ = [("l", ctypes.c_uint32), ("h", ctypes.c_uint32)]
            i, k, u = FT(), FT(), FT(); ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
            v = lambda f: (f.h << 32) | f.l
            cur = (v(i), v(k) + v(u))
            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32)] + [(n, ctypes.c_uint64) for n in ("a", "b", "c", "d", "e", "f", "g")]
            ms = MS(); ms.dwLength = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
            m["ram_percent"] = float(ms.dwMemoryLoad)
        else:
            f = [int(x) for x in open("/proc/stat").readline().split()[1:8]]
            cur = (f[3] + f[4], sum(f))
            mi = dict((l.split(":")[0], int(l.split()[1])) for l in open("/proc/meminfo") if l.split()[1].isdigit())
            m["ram_percent"] = round(100 * (1 - mi["MemAvailable"] / mi["MemTotal"]), 1)
        if _cpu_prev:
            idle, tot = cur[0] - _cpu_prev[0], cur[1] - _cpu_prev[1]
            if os.name != "nt" and tot > 0:
                m["cpu_percent"] = round(100 * (1 - idle / tot), 1)
            elif tot > 0:
                m["cpu_percent"] = round(100 * (1 - idle / tot), 1)
        _cpu_prev = cur
    except Exception as e:
        m["error"] = str(e)[:120]
    if SAFE["gpu_temp_c"] is not None or SAFE.get("gpu_hot_spot_c") is not None:
        hot = SAFE.get("gpu_hot_spot_c") if SAFE.get("gpu_hot_spot_c") is not None else SAFE["gpu_temp_c"]
        m["gpu_hotspot_c"] = hot
        m["gpu_hot_spot_c"] = hot
        m["gpu_source"] = SAFE.get("source")
        m["sensor_source"] = SAFE.get("sensor") or SAFE.get("source")
        # Отдельного датчика ядра может не быть: не подставляем Hot Spot в gpu_temperature_c как «ядро».
    if GPU_EXTRA["load"] is not None:
        m["gpu_percent"] = GPU_EXTRA["load"]; m.setdefault("gpu_source", GPU_EXTRA["source"])
        if GPU_EXTRA["vram_used_mb"] is not None and GPU_EXTRA["vram_total_mb"]:
            m["vram_used_gb"] = round(GPU_EXTRA["vram_used_mb"] / 1024, 2); m["vram_total_gb"] = round(GPU_EXTRA["vram_total_mb"] / 1024, 2)
    m["safe70"] = dict(SAFE)
    return m

# ---------- прогресс по контракту ----------
def progress_receipt():
    r = None
    if os.path.exists(RECEIPT):
        try:
            with open(RECEIPT, "r", encoding="utf-8") as f:
                r = json.load(f)
        except Exception as e:
            r = PC._hold("RECEIPT_UNREADABLE: " + str(e)[:80])
    if not isinstance(r, dict):
        r = PC._hold("NO_RECEIPT_ON_PC (" + RECEIPT + ")")
    verified = (r.get("schema") == "nox-progress-receipt-v1" and r.get("status") == "VERIFIED_COMPLETE" and r.get("complete") is True
                and r.get("weightUpdateVerified") is True and r.get("windowsSyncVerified") is True
                and r.get("attestation") == "LOCAL_WEIGHT_AND_TRAINER_STATE_SHA256_CHECKED")
    r = dict(r)
    if not verified:
        r["nox_prime_born_at"] = None
    r["receiptPath"] = RECEIPT
    r["host"] = "NOX_CHAT_V24.1"
    return r

# ---------- BIRTH_EVENT (pod1 seed_gpu/scripts/birth.py) — только чтение ----------
BIRTH_PATHS = [os.environ.get("NOX_BIRTH_EVENT") or "", os.path.join(HOME, "models", "BIRTH_EVENT.json"), os.path.join(HOME, "progress", "BIRTH_EVENT.json")]
def birth_event():
    for p in BIRTH_PATHS:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f: ev = json.load(f)
                with open(p, "rb") as f: dig = hashlib.sha256(f.read()).hexdigest()
                checks = ev.get("checks") if isinstance(ev.get("checks"), dict) else {}
                return {"status": "FOUND", "path": p, "file_sha256": dig, "event": ev.get("event"), "checked_at": ev.get("checked_at"),
                        "claimed_born_at": ev.get("nox_prime_born_at"), "checks": checks,
                        "all_checks_pass": bool(checks) and all(v is True for v in checks.values()),
                        "merged_shard_sha256": ev.get("merged_shard_sha256"), "train": ev.get("train"),
                        "note": "BIRTH_EVENT — заявка pod1; рождение в чате подтверждается только квитанцией VERIFIED_COMPLETE"}
            except Exception as e:
                return {"status": "UNREADABLE", "path": p, "error": str(e)[:160]}
    return {"status": "HOLD", "reason": "NO_BIRTH_EVENT_ON_PC", "paths": [p for p in BIRTH_PATHS if p]}

def verified_birth():
    """Рождение признаётся в чате, если: BIRTH_EVENT от pod1 со всеми проверками true, его SHA256 совпал со строкой
    в SHA256SUMS рядом с весами, и в той же SHA256SUMS стоит SHA256 GGUF, который launcher проверил и собрал в nox-prime."""
    ev = birth_event(); man = model_manifest() or {}
    out = {"born_at": None, "reason": None}
    if ev.get("status") != "FOUND": out["reason"] = "нет BIRTH_EVENT на ПК"; return out
    if not ev.get("all_checks_pass"): out["reason"] = "в BIRTH_EVENT не все проверки пройдены"; return out
    sums = {}
    p = os.path.join(os.path.dirname(ev["path"]), "SHA256SUMS")
    try:
        for line in open(p, encoding="utf-8"):
            a = line.split()
            if len(a) >= 2 and re.fullmatch(r"[0-9a-fA-F]{64}", a[0]): sums[os.path.basename(a[-1].lstrip("*"))] = a[0].lower()
    except Exception: out["reason"] = "нет SHA256SUMS рядом с BIRTH_EVENT"; return out
    if sums.get("BIRTH_EVENT.json") != ev.get("file_sha256"): out["reason"] = "SHA256 BIRTH_EVENT не совпал с SHA256SUMS"; return out
    gg = os.path.basename(str(man.get("file") or "").replace("\\", "/"))
    if not man.get("sha256") or sums.get(gg) != man.get("sha256"): out["reason"] = "GGUF nox-prime не совпал с SHA256SUMS рождения"; return out
    if man.get("test_source"): out["reason"] = "тестовый стенд"; return out
    out["born_at"] = ev.get("claimed_born_at"); out["gguf_sha256"] = man.get("sha256")
    return out

def sync_birth():
    vb = verified_birth()
    if vb["born_at"]:
        with LOCK: CORE.self_model.born_at = vb["born_at"]
    return vb

# ---------- погода (сервер-прокси Open-Meteo, без ключа и без трекинга; браузер ходит только на 127.0.0.1) ----------
WEATHER = {"at": 0, "data": None}
WX_CODES = {0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман", 48: "изморозь", 51: "морось", 53: "морось", 55: "сильная морось",
            61: "небольшой дождь", 63: "дождь", 65: "ливень", 71: "небольшой снег", 73: "снег", 75: "сильный снег", 80: "ливни", 81: "ливни", 82: "сильные ливни", 95: "гроза", 96: "гроза с градом", 99: "гроза с градом"}
def weather():
    if os.environ.get("NOX_WEATHER", "on") == "off":
        return {"status": "OFF", "note": "погода выключена (NOX_WEATHER=off)"}
    if WEATHER["data"] and time.time() - WEATHER["at"] < 900: return WEATHER["data"]
    lat, lon, place = os.environ.get("NOX_WEATHER_LAT", "40.4168"), os.environ.get("NOX_WEATHER_LON", "-3.7038"), os.environ.get("NOX_WEATHER_PLACE", "Мадрид")
    url = ("https://api.open-meteo.com/v1/forecast?latitude=" + lat + "&longitude=" + lon +
           "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min&forecast_days=1&timezone=Europe%2FMadrid")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "NOX-CHAT-V22"}), timeout=6) as r: j = json.loads(r.read().decode("utf-8"))
        c, d = j.get("current", {}), j.get("daily", {})
        data = {"status": "READY", "place": place, "temp_c": c.get("temperature_2m"), "feels_c": c.get("apparent_temperature"), "humidity": c.get("relative_humidity_2m"),
                "wind_kmh": c.get("wind_speed_10m"), "code": c.get("weather_code"), "text": WX_CODES.get(c.get("weather_code"), "—"),
                "max_c": (d.get("temperature_2m_max") or [None])[0], "min_c": (d.get("temperature_2m_min") or [None])[0], "observed": c.get("time"), "source": "open-meteo.com"}
        WEATHER.update(at=time.time(), data=data); return data
    except Exception as e:
        if WEATHER["data"]: return {**WEATHER["data"], "status": "STALE", "note": "нет сети — показаны последние данные"}
        return {"status": "OFFLINE", "place": place, "note": "нет сети — погода недоступна", "error": str(e)[:80]}


# ---------- публичные сервисы (Open-Meteo, Frankfurter, RSS) по нажатию ----------
_UA = {"User-Agent": "NOX-CHAT-V24"}
_SVC_CACHE = {}

def _http_json(url, timeout=8):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def _http_text(url, timeout=8, accept="application/rss+xml, application/atom+xml, application/xml, text/xml, text/plain"):
    req = urllib.request.Request(url, headers={**_UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

def geocode_city(city):
    q = (city or "").strip()
    if not q:
        return {"status": "HOLD", "places": [], "reason": "укажите город"}
    url = "https://geocoding-api.open-meteo.com/v1/search?name=" + urllib.parse.quote(q) + "&count=5&language=ru&format=json"
    try:
        j = _http_json(url)
        places = []
        for it in (j.get("results") or [])[:5]:
            places.append({
                "name": it.get("name") or q,
                "country": it.get("country") or "",
                "admin": it.get("admin1") or "",
                "latitude": it.get("latitude"),
                "longitude": it.get("longitude"),
            })
        return {"status": "READY", "provider": "geocoding-api.open-meteo.com", "places": places}
    except Exception as e:
        return {"status": "OFFLINE", "places": [], "reason": "нет сети — геокодирование недоступно", "error": str(e)[:80]}

def weather_for(lat=None, lon=None, place=None, body=None):
    body = body or {}
    try:
        lat = float(body.get("latitude") if body.get("latitude") is not None else (lat if lat is not None else os.environ.get("NOX_WEATHER_LAT", "40.4168")))
        lon = float(body.get("longitude") if body.get("longitude") is not None else (lon if lon is not None else os.environ.get("NOX_WEATHER_LON", "-3.7038")))
    except Exception:
        return {"status": "HOLD", "reason": "неверные координаты"}
    place = place or body.get("name") or os.environ.get("NOX_WEATHER_PLACE", "Мадрид")
    key = f"{lat:.3f},{lon:.3f}"
    nowt = time.time()
    hit = _SVC_CACHE.get("wx:" + key)
    if hit and nowt - hit[0] < 300:
        return {**hit[1], "cached": True}
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
           "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
           "&daily=temperature_2m_max,temperature_2m_min&forecast_days=7&timezone=auto") % (lat, lon)
    try:
        j = _http_json(url)
        c, d, u = j.get("current") or {}, j.get("daily") or {}, (j.get("current_units") or {})
        days = d.get("time") or []
        highs = d.get("temperature_2m_max") or []
        lows = d.get("temperature_2m_min") or []
        forecast = [{"date": days[i], "high": highs[i] if i < len(highs) else None, "low": lows[i] if i < len(lows) else None} for i in range(len(days))]
        data = {
            "status": "READY", "provider": "open-meteo.com", "place": place,
            "latitude": lat, "longitude": lon, "timezone": j.get("timezone"),
            "current": c, "units": u or {"temperature_2m": "°C", "wind_speed_10m": "км/ч"},
            "forecast": forecast, "cached": False,
            # совместимость со старой панелью
            "temp_c": c.get("temperature_2m"), "feels_c": c.get("apparent_temperature"),
            "humidity": c.get("relative_humidity_2m"), "wind_kmh": c.get("wind_speed_10m"),
            "code": c.get("weather_code"), "text": WX_CODES.get(c.get("weather_code"), "—"),
            "max_c": (highs or [None])[0], "min_c": (lows or [None])[0], "observed": c.get("time"), "source": "open-meteo.com",
        }
        _SVC_CACHE["wx:" + key] = (nowt, data)
        return data
    except Exception as e:
        if hit:
            return {**hit[1], "status": "STALE", "cached": True, "note": "нет сети — показаны последние данные"}
        return {"status": "OFFLINE", "place": place, "note": "нет сети — погода недоступна", "error": str(e)[:80],
                "current": {}, "units": {}, "forecast": []}

def fx_rate(base="EUR", quote="USD"):
    base = (base or "EUR").strip().upper()
    quote = (quote or "USD").strip().upper()
    if not (len(base) == 3 and len(quote) == 3 and base.isalpha() and quote.isalpha()):
        return {"status": "HOLD", "reason": "нужны коды ISO из трёх букв"}
    key = f"fx:{base}:{quote}"
    nowt = time.time()
    hit = _SVC_CACHE.get(key)
    if hit and nowt - hit[0] < 300:
        return {**hit[1], "cached": True}
    try:
        latest = _http_json("https://api.frankfurter.app/latest?from=" + base + "&to=" + quote)
        rate = (latest.get("rates") or {}).get(quote)
        end = latest.get("date") or ""
        history = []
        try:
            import datetime as _dt
            start = (_dt.date.fromisoformat(end) - _dt.timedelta(days=14)).isoformat() if end else ""
            if start:
                hist = _http_json("https://api.frankfurter.app/%s..%s?from=%s&to=%s" % (start, end, base, quote))
                for day, rates in sorted((hist.get("rates") or {}).items()):
                    if quote in rates:
                        history.append({"date": day, "rate": rates[quote]})
        except Exception:
            history = [{"date": end, "rate": rate}] if rate is not None else []
        data = {"status": "READY", "provider": "api.frankfurter.app", "base": base, "quote": quote,
                "rate": rate, "rate_date": end, "history": history or ([{"date": end, "rate": rate}] if rate is not None else [])}
        _SVC_CACHE[key] = (nowt, data)
        return data
    except Exception as e:
        if hit:
            return {**hit[1], "status": "STALE", "note": "нет сети — показан последний курс"}
        return {"status": "OFFLINE", "base": base, "quote": quote, "reason": "нет сети — курс недоступен", "error": str(e)[:80]}

def news_feed():
    url = os.environ.get("NOX_NEWS_RSS") or "https://feeds.bbci.co.uk/news/rss.xml"
    key = "news:" + url
    nowt = time.time()
    hit = _SVC_CACHE.get(key)
    if hit and nowt - hit[0] < 300:
        return {**hit[1], "cached": True}
    try:
        import xml.etree.ElementTree as ET
        raw = _http_text(url)
        root = ET.fromstring(raw)
        items = []
        for node in list(root.iter()):
            tag = node.tag.split("}")[-1].lower()
            if tag not in ("item", "entry"):
                continue
            title = ""
            link = ""
            published = ""
            for ch in list(node):
                ct = ch.tag.split("}")[-1].lower()
                if ct == "title" and not title:
                    title = (ch.text or "").strip()
                elif ct == "link":
                    link = (ch.get("href") or ch.text or link or "").strip()
                elif ct in ("pubdate", "published", "updated") and not published:
                    published = (ch.text or "").strip()
            if title and link:
                items.append({"title": title[:300], "url": link, "published": published})
            if len(items) >= 15:
                break
        data = {"status": "READY", "provider": urllib.parse.urlparse(url).netloc, "source": url,
                "observed_at": now(), "items": items}
        _SVC_CACHE[key] = (nowt, data)
        return data
    except Exception as e:
        if hit:
            return {**hit[1], "status": "STALE", "note": "нет сети — показана последняя лента"}
        return {"status": "OFFLINE", "provider": urllib.parse.urlparse(url).netloc, "items": [], "observed_at": now(),
                "reason": "лента недоступна", "error": str(e)[:80]}

def calendar_ics(events=None, title="NOX"):
    ev = events if isinstance(events, list) else []
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//NOX//CHAT V24//RU", "CALSCALE:GREGORIAN"]
    if not ev:
        # пустой календарь-заготовка: владелец дополнит событиями проектов
        lines += ["BEGIN:VEVENT", "SUMMARY:" + (title or "NOX"), "DTSTAMP:" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), "UID:nox-empty@local", "END:VEVENT"]
    for i, e in enumerate(ev[:200]):
        if not isinstance(e, dict):
            continue
        summ = str(e.get("title") or e.get("summary") or "Событие").replace("\n", " ")[:180]
        start = str(e.get("start") or e.get("dtstart") or time.strftime("%Y%m%d")).replace("-", "")[:16]
        uid = str(e.get("uid") or ("nox-%s-%s" % (i, int(time.time()))))
        lines += ["BEGIN:VEVENT", "UID:" + uid, "SUMMARY:" + summ, "DTSTART:" + start, "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ---------- визуальные настройки (workspace.js из WEB V21) ----------
SETTINGS_PATH = os.path.join(HOME, "settings", "nox-chat-v22-settings.json")
SESSION_TOKEN = uuid.uuid4().hex
ADDRESS_FORMS = ("мессир", "мой лорд", "барон", "создатель")
SETTING_KEYS = {"mode": ("BALANCED", "MAX", "ECO"), "motion": ("system", "reduce", "full"),
                "theme": ("amber", "contrast", "cosmic-blue", "void-purple", "graphite", "arctic", "ember"),
                "finish": ("graphite", "obsidian", "titanium"), "language": ("ru", "es"), "buttonStyle": ("riveted", "seamless", "outline"),
                "layout": ("compact", "balanced", "focus"), "musicStyle": ("industrial", "desert", "orbital"), "musicVolume": ("quiet", "normal", "full"),
                "address": ("auto",) + ADDRESS_FORMS, "fx": ("on", "off")}
BOOL_KEYS = ("voice", "privacy", "notifications", "musicEnabled", "musicAdaptive")
V22_DEFAULTS = {"theme": "amber", "finish": "obsidian", "mode": "MAX", "motion": "system", "address": "auto", "fx": "on"}  # «Классика»: чёрное солнце
def load_settings():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f: return {**V22_DEFAULTS, **json.load(f)}, True
    except Exception: return dict(V22_DEFAULTS), False
def save_settings(delta):
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f: cur = json.load(f)
    except Exception: cur = {}
    for k, v in (delta or {}).items():
        if k in SETTING_KEYS and v in SETTING_KEYS[k]: cur[k] = v
        elif k in BOOL_KEYS and isinstance(v, bool): cur[k] = v
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(cur, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SETTINGS_PATH)
    return {**V22_DEFAULTS, **cur}

# ---------- диалоги ----------
def db_exec(sql, args=()):
    with LOCK:
        cur = CONN.execute(sql, args); CONN.commit(); return cur

def ensure_dialog(did, title):
    with LOCK:
        if did and CONN.execute("select 1 from chat_dialogs where id=?", (did,)).fetchone():
            return did
        did = did or ("D-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
        CONN.execute("insert into chat_dialogs(id,title,created_at) values(?,?,?)", (did, (title or "Диалог NOX")[:140], now())); CONN.commit()
        return did

def add_msg(did, role, content, model, status, rid):
    if role == "assistant" and model:  # честная метка источника в S03: тестовые ответы помечены навсегда
        src = answer_source("NOX_PRIME")[0]
        if src in ("MOCK", "HARNESS"): model = f"{model} [{src}]"
    return db_exec("insert into chat_messages(dialog_id,role,content,model,status,request_id,sha256,created_at) values(?,?,?,?,?,?,?,?)",
                   (did, role, content, model, status, rid, sha(content), now())).lastrowid

def dialog_messages(did, limit=200):
    with LOCK:
        rows = CONN.execute("select id,role,content,model,status,request_id,sha256,created_at from chat_messages where dialog_id=? order by id desc limit ?", (did, limit)).fetchall()[::-1]
    return [dict(zip(("id", "role", "content", "model", "status", "request_id", "sha256", "created_at"), r)) for r in rows]

def dialogs():
    with LOCK:
        rows = CONN.execute("select d.id,coalesce((select t.title from chat_dialog_titles t where t.dialog_id=d.id order by t.id desc limit 1),d.title),d.created_at,count(m.id),max(m.created_at) from chat_dialogs d left join chat_messages m on m.dialog_id=d.id group by d.id order by coalesce(max(m.id),0) desc, d.created_at desc").fetchall()
        cm = CONN.execute("select count(*) from creator_messages").fetchone()[0]
    return {"status": "READY", "creator_messages_total": cm, "db": DB_PATH,
            "dialogs": [dict(zip(("id", "title", "created_at", "messages", "last_at"), r)) for r in rows]}

def memory_view():
    with LOCK:
        stats = CORE.memory_stats()
        seg = {lv: [dict(zip(("content", "provenance", "significance", "created_at"), r)) for r in CORE.mem.read(lv, 3)] for lv in SC.LEVELS}
        # M7 считает и Genesis Ledger — показываем его записи, иначе список пуст при счётчике > 0
        led = CONN.execute("select seq,event,ts,hash from genesis_ledger order by seq desc limit 4").fetchall()[::-1]
        seg["M7_autobiography"] = [{"content": f"Genesis Ledger №{q}: {ev}", "provenance": "genesis_ledger · " + h[:12], "significance": 1.0, "created_at": ts} for q, ev, ts, h in led] + seg.get("M7_autobiography", [])[-3:]
        ok = CORE.ledger_verify()
    return {"status": "READY", "stats": stats, "segments": seg, "levels": SC.LEVEL_DESC, "ledger_chain_ok": ok, "db": DB_PATH}

RUNS = {}  # request_id -> {"stop": None|reason}

def build_messages(did, text):
    """SELF-CONTEXT + S03 + лексический RAG. Бюджет до Ollama ~1.5 с; без bge-m3 и без смены модели в VRAM."""
    t_all = time.perf_counter()
    timings = {}
    t0 = time.perf_counter()
    sync_birth()
    timings["sync_birth_ms"] = int((time.perf_counter() - t0) * 1000)
    rag_info = {"mode": "skip", "ms": 0}
    kn_brief = ""
    with LOCK:
        t0 = time.perf_counter()
        mem = LIVE.retrieve(CONN, text, k=8, use_embed=False)
        if SOUL is not None:
            try:
                mem = SOUL.rerank(mem, text, SOUL.load_state(), SOUL.read_episodes(limit=12), k=5)
            except Exception:
                mem = mem[:5]
        else:
            mem = mem[:5]
        ident = bool(IDENTITY and IDENTITY.is_identity_intent(text))
        if ident:
            try:
                mem = IDENTITY.downrank_memory_hits(mem, CONN, source="s03")
                mem = [h for h in mem if not IDENTITY.is_stale_prebirth(h[2] if len(h) > 2 else "")]
            except Exception:
                pass
        fact = SC.remember_command(text)
        CORE.perceive(text, mem)
        if fact:
            CORE.remember_fact(fact, LIVE.remember)
        # Полный SELF-CONTEXT (часы, счётчики, паспорт) больше не кладём в system: он ломал prefix-cache и раздувал prefill.
        # Якоря личности живут в стабильном persona_prefix (байт-в-байт). Ниже — только короткая живая строка.
        ctx = []
        if ident:
            hunger = getattr(getattr(CORE, "state", None), "hunger", None)
            ctx.append(IDENTITY.canon_pin(hunger))
        try:
            live = CORE.compact_live_context() if hasattr(CORE, "compact_live_context") else ""
            if live:
                ctx.append(live)
        except Exception:
            pass
        form = (load_settings()[0].get("address") or "auto")
        if form in ADDRESS_FORMS:
            ctx.append("Сейчас для обращения к создателю предпочтительна форма «%s»." % form)
        prev = [m["content"] for m in dialog_messages(did, 12) if m["role"] == "assistant" and m["status"] == "done"][-3:]
        if ident and IDENTITY is not None:
            prev = IDENTITY.filter_context_texts(prev, CONN, source="dialog_hist")
        sent = []
        for prev_t in prev:
            for x in re.split(r"(?<=[.!?…])\s+", prev_t):
                x = x.strip()
                if 12 <= len(x) <= 160 and x not in sent: sent.append(x)
        if sent:
            ctx.append("НЕ ПОВТОРЯЙ ДОСЛОВНО свои прошлые фразы (скажи по-новому или не говори вовсе): " + " | ".join(sent[-8:]) +
                       ". Не заканчивай ответ дежурным «жду ваших инструкций» и не повторяй «моя уверенность высока».")
        CORE.mem.write("M0_working", f"ход {CORE.state.turns}: «{text[:200]}» (диалог {did})", "chat_v21", 0.3)
        if mem:
            ctx.append("ВОСПОМИНАНИЯ ИЗ ПАМЯТИ S03 (используй, если относится к вопросу):\n" + "\n".join(f"- [{k} {ts[:16]}] {t[:400]}" for s, k, t, ts in mem))
        if LIVE.RECALL.search(text):
            cm = CONN.execute("select content,created_at from creator_messages order by id desc limit 30").fetchall()[::-1]
            ctx.append("ВСЕ ПОСЛЕДНИЕ СООБЩЕНИЯ СОЗДАТЕЛЯ (дословно):\n" + "\n".join(f"- [{ts[:16]}] {t}" for t, ts in cm))
        timings["s03_ms"] = int((time.perf_counter() - t0) * 1000)

    budget = 1.5
    if RAG_FAST is not None:
        try:
            budget = float(getattr(RAG_FAST, "BUDGET_SEC", 1.5) or 1.5)
        except Exception:
            budget = 1.5
    boxes = {"kn": None, "tools": None, "soul": None}

    def _kn_job():
        try:
            if RAG_FAST is not None and KN is not None:
                dbp = getattr(KN, "DB_PATH", None)
                boxes["kn"] = RAG_FAST.retrieve(text, k=3, db_path=dbp, budget=min(budget, 0.8))
            elif KN is not None:
                boxes["kn"] = {"hits": KN.retrieve(text, k=5, use_embed=False), "mode": "legacy-lex", "ms": 0}
        except Exception as e:
            boxes["kn"] = {"hits": [], "mode": "error", "ms": 0, "reason": type(e).__name__}

    def _tools_job():
        brief = ""
        try:
            if KTOOLS is not None and HELPERS is not None and not HELPERS.is_private(text):
                bundle = KTOOLS.lookup(text)
                brief = KTOOLS.format_for_context(bundle)
        except Exception:
            brief = ""
        boxes["tools"] = brief

    def _soul_job():
        try:
            if SOUL is None:
                boxes["soul"] = None
                return
            st = SOUL.load_state()
            thought = SOUL.inner_monologue(text, st)
            st.setdefault("awareness", {})["hidden_thought"] = thought
            due = []
            if SURPRISE is not None:
                due = SURPRISE.due_items(Path(MEMDIR))
            boxes["soul"] = SOUL.variable_soul_context(st, reminders=due, thought=thought)
        except Exception:
            boxes["soul"] = None

    t0 = time.perf_counter()
    jobs = [
        threading.Thread(target=_kn_job, name="nox-rag", daemon=True),
        threading.Thread(target=_tools_job, name="nox-ktools", daemon=True),
        threading.Thread(target=_soul_job, name="nox-soul", daemon=True),
    ]
    for j in jobs:
        j.start()
    deadline = time.time() + budget
    for j, name in zip(jobs, ("kn", "tools", "soul")):
        remain = max(0.01, deadline - time.time())
        j.join(timeout=remain)
        timings[name + "_alive"] = j.is_alive()
    timings["parallel_ms"] = int((time.perf_counter() - t0) * 1000)

    rag = boxes.get("kn") or {}
    rag_info = {"mode": rag.get("mode") or "skip", "ms": rag.get("ms") or 0}
    try:
        kn_ctx = None
        hits = rag.get("hits") or []
        if IDENTITY is not None and IDENTITY.is_identity_intent(text):
            hits = IDENTITY.filter_rag_hits(hits, CONN)
        if hits:
            if RAG_FAST is not None:
                kn_ctx = RAG_FAST.format_context(hits, limit_each=280)
            elif KN is not None:
                kn_ctx = KN.format_context(hits, limit_each=280)
        if kn_ctx:
            if len(kn_ctx) > 900:
                kn_ctx = kn_ctx[:900].rsplit(" ", 1)[0] + "…"
            ctx.append(kn_ctx)
    except Exception:
        pass
    kn_brief = boxes.get("tools") or ""
    if kn_brief:
        ctx.append(kn_brief)
    if boxes.get("soul"):
        ctx.append(boxes["soul"])

    hist = [{"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
            for m in dialog_messages(did, 7)[:-1] if m["content"].strip()]
    if IDENTITY is not None and IDENTITY.is_identity_intent(text):
        clean = []
        for h in hist:
            if h["role"] == "assistant" and IDENTITY.is_stale_prebirth(h["content"]):
                IDENTITY.mark_stale(CONN, h["content"], "dialog_hist")
                continue
            clean.append(h)
        hist = clean
    # Один system-сообщение: Ollama 0.40.x отвечает HTTP 500 на два подряд role=system.
    # Стабильный persona-префикс остаётся в начале текста — для prefix cache + keep_alive.
    stable = SOUL.persona_prefix() if SOUL is not None else ""
    try:
        vmax = int(os.environ.get("NOX_VAR_CTX_MAX", "1400"))
    except Exception:
        vmax = 1400
    if vmax > 0:  # WS1 2026-11-11: first-token budget <2 s -> trim the largest parts first, keep short anchors intact
        for _ in range(12):
            excess = sum(len(x) for x in ctx) + 2 * max(0, len(ctx) - 1) - vmax
            if excess <= 0 or not ctx:
                break
            i = max(range(len(ctx)), key=lambda j: len(ctx[j]))
            if len(ctx[i]) <= 260:
                break
            keep = max(240, len(ctx[i]) - excess)
            ctx[i] = ctx[i][:keep].rsplit(" ", 1)[0] + "…"
    variable = "\n\n".join(ctx)
    if stable and variable:
        system = stable + "\n\n" + variable
    else:
        system = stable or variable
    msgs = [{"role": "system", "content": system}] if system else []
    timings["build_total_ms"] = int((time.perf_counter() - t_all) * 1000)
    timings["sys_stable_chars"] = len(stable); timings["sys_var_chars"] = len(variable)
    timings["var_parts"] = [len(x) for x in ctx]; timings["hist_chars"] = sum(len(h["content"]) for h in hist[-6:])
    return msgs + hist[-6:] + [{"role": "user", "content": text}], fact, len(mem), kn_brief, timings, rag_info

# ---------- живой прогресс: C:\NOX\progress\status.json + локальный индексер ----------
STATUS_JSON = os.environ.get("NOX_STATUS_JSON") or os.path.join(HOME, "progress", "status.json")
PAUSE_INDEX = os.path.join(MEMDIR, "PAUSE_INDEX")

_PAUSE_BEAT = {"on": False}

def _set_index_pause(on):
    """Сигнал индексатору уступить GPU (PAUSE_INDEX) и выгрузить bge-m3 на время генерации."""
    try:
        if on:
            os.makedirs(MEMDIR, exist_ok=True)
            with open(PAUSE_INDEX, "w", encoding="utf-8") as f:
                f.write(now())
            if not _PAUSE_BEAT.get("on"):
                _PAUSE_BEAT["on"] = True
                threading.Thread(target=_pause_index_heartbeat, name="nox-pause-idx", daemon=True).start()
            threading.Thread(target=_unload_embed_for_chat, name="nox-unload-bge", daemon=True).start()
        else:
            _PAUSE_BEAT["on"] = False
            if os.path.isfile(PAUSE_INDEX):
                os.remove(PAUSE_INDEX)
    except Exception:
        pass

def _pause_index_heartbeat():
    """Обновляет mtime PAUSE_INDEX, пока идёт ответ, чтобы флаг не протух (~90 с)."""
    while _PAUSE_BEAT.get("on"):
        try:
            if os.path.isfile(PAUSE_INDEX):
                os.utime(PAUSE_INDEX, None)
            else:
                with open(PAUSE_INDEX, "w", encoding="utf-8") as f:
                    f.write(now())
        except Exception:
            pass
        for _ in range(20):
            if not _PAUSE_BEAT.get("on"):
                return
            time.sleep(1)

def _unload_embed_for_chat():
    """Снять bge-m3 с GPU, не блокируя сборку контекста. Игнор ошибок."""
    try:
        body = json.dumps({"model": "bge-m3", "keep_alive": 0, "prompt": ""}).encode("utf-8")
        req = urllib.request.Request(OLLAMA + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=8).read()
    except Exception:
        pass

def _num_ok(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None

def indexer_live():
    out = {"status": "HOLD", "chunks_embedded": None, "chunks_total": None, "pending": None,
           "rate_per_min": None, "safe70": dict(SAFE), "db": None, "paused_for_chat": os.path.isfile(PAUSE_INDEX)}
    if KN is None:
        out["reason"] = "nox_knowledge не подключён"
        return out
    try:
        conn = KN.connect()
        st = KN.stats(conn)
        conn.close()
        emb = int(st.get("embedded") or st.get("chunks_embedded") or 0)
        total = int(st.get("chunks") or st.get("chunks_total") or emb)
        pending = int(st.get("pending") or max(0, total - emb))
        out.update(status="READY", chunks_embedded=emb, chunks_total=total, pending=pending,
                   db=getattr(KN, "DB_PATH", None), stats=st,
                   gpu_hot_spot_c=SAFE.get("gpu_hot_spot_c") or SAFE.get("gpu_temp_c"),
                   safe70_decision=SAFE.get("decision"), safe70_reason=SAFE.get("reason"),
                   safe70_streak=SAFE.get("streak_70"), sensor=SAFE.get("sensor"))
        # rate from optional meta or status.json indexer
        try:
            rate = st.get("rate_per_min") or st.get("embed_rate")
            out["rate_per_min"] = _num_ok(rate)
        except Exception:
            pass
        try:
            if out.get("rate_per_min") is None and os.path.isfile(STATUS_JSON):
                raws = json.load(open(STATUS_JSON, encoding="utf-8"))
                ixj = raws.get("indexer") if isinstance(raws, dict) else None
                if isinstance(ixj, dict):
                    out["rate_per_min"] = out["rate_per_min"] or _num_ok(ixj.get("rate_per_min"))
        except Exception:
            pass
        if out.get("rate_per_min") and pending and out["rate_per_min"] > 0:
            out["eta_sec"] = pending / float(out["rate_per_min"]) * 60.0
    except Exception as e:
        out["reason"] = str(e)[:160]
    return out

def trainer_live():
    path = STATUS_JSON
    out = {"status": "HOLD", "path": path, "reason": "нет файла статуса", "step": None, "rows_done": None, "rows_total": None,
           "holdout_improvement_pct": None, "tok_s": None, "step_time_sec": None, "gpu_percent": None, "vram_used_gb": None, "vram_total_gb": None,
           "ram_percent": None, "eta_sec": None, "gguf_status": None, "gguf_path": None, "updated_at": None, "source": None}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        out["reason"] = "STATUS_UNREADABLE: " + str(e)[:120]
        return out
    tr = raw.get("trainer") if isinstance(raw, dict) and isinstance(raw.get("trainer"), dict) else (raw if isinstance(raw, dict) else {})
    def g(*keys):
        for k in keys:
            if tr.get(k) is not None:
                return tr.get(k)
            if raw.get(k) is not None:
                return raw.get(k)
        return None
    out.update(status="READY", reason=None, source="status.json",
               step=g("step", "global_step"),
               rows_done=g("rows_done", "samples_done", "seen"),
               rows_total=g("rows_total", "samples_total", "total"),
               holdout_improvement_pct=_num_ok(g("holdout_improvement_pct", "holdout_delta_pct", "quality_gain_pct")),
               tok_s=_num_ok(g("tok_s", "tokens_per_second", "tps")),
               step_time_sec=_num_ok(g("step_time_sec", "step_sec", "secs_per_step", "step_time")),
               gpu_percent=_num_ok(g("gpu_percent", "gpu")),
               vram_used_gb=_num_ok(g("vram_used_gb", "vram_used")),
               vram_total_gb=_num_ok(g("vram_total_gb", "vram_total")),
               ram_percent=_num_ok(g("ram_percent", "ram")),
               eta_sec=_num_ok(g("eta_sec", "eta_seconds", "eta")),
               gguf_status=g("gguf_status", "gguf"),
               gguf_path=g("gguf_path"),
               updated_at=g("updated_at", "timestamp", "at") or (raw.get("updated_at") if isinstance(raw, dict) else None))
    if out["gguf_status"] is None:
        out["gguf_status"] = "HOLD"
    return out

def prey_board():
    try:
        from predator import prey as _prey
        info = _prey.load(MEMDIR)
        return {"count": info.get("count") or 0, "names": info.get("names") or [],
                "facts": info.get("facts"), "path": info.get("path"), "status": info.get("status")}
    except Exception as e:
        return {"count": 0, "names": [], "facts": "Реестр жертв не прочитан — имён не называю.", "status": "UNREADABLE", "error": type(e).__name__}


def live_board():
    tr, ix = trainer_live(), indexer_live()
    prey = prey_board()
    soul = None
    if SOUL is not None:
        try:
            st = SOUL.public_soul()
            soul = {"mood": st.get("mood"), "glow": st.get("glow"), "hunger_for_knowledge": st.get("hunger_for_knowledge"), "hf": st.get("hf"), "simulated": True}
        except Exception:
            soul = None
    tasks = None
    if SELF_TASKS is not None:
        try:
            tasks = SELF_TASKS.snapshot()
        except Exception:
            tasks = None
    return {"status": "READY", "host": "NOX_CHAT_V24.1", "trainer": tr, "indexer": ix,
            "safe70": dict(SAFE), "prey": prey, "absorbed": prey.get("count") or 0,
            "soul": soul, "self_tasks": tasks, "polled_at": now()}

def _start_progress_bridge():
    """Лёгкий мост C:\\NOX\\progress\\status.json, без GPU и без трогания индексатора."""
    root = os.path.join(ROOT, "progress")
    script = os.path.join(root, "nox_progress_updater.py")
    if not os.path.isfile(script):
        return
    env = dict(os.environ)
    env.setdefault("NOX_HOME", HOME)
    env.setdefault("NOX_PROGRESS_POLL", "90")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    py = sys.executable.replace("python.exe", "pythonw.exe") if os.name == "nt" else sys.executable
    if os.name == "nt" and not os.path.isfile(py):
        py = sys.executable
    subprocess.Popen([py, script], cwd=root, env=env, creationflags=flags,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True)


def ollama_options():
    def env_int(name, default):
        try:
            return int(os.environ.get(name, default))
        except Exception:
            return default
    # RX 6650M 8 GB: keep the model loaded, modest ctx, leave headroom for KV + (paused) embedder.
    # WS1 2026-11-11: runner options (num_ctx/num_gpu/num_thread/num_batch) differ from Ollama defaults forced a
    # 6 s model RELOAD whenever anyone else called nox with defaults. Send them only if explicitly set in env;
    # otherwise the Modelfile defaults (num_ctx 8192, batch 512, full GPU) are used by everyone -> nox stays warm.
    o = {"num_predict": env_int("NOX_NUM_PREDICT", 400)}
    for k, e in (("num_ctx", "NOX_NUM_CTX"), ("num_gpu", "NOX_NUM_GPU"), ("num_thread", "NOX_NUM_THREAD"), ("num_batch", "NOX_NUM_BATCH")):
        if os.environ.get(e):
            o[k] = env_int(e, 0)
    return o

KEEP_ALIVE = os.environ.get("NOX_KEEP_ALIVE", "-1m")  # WS1 2026-11-11: forever by default

def warmup_model():
    name, meta, kind = pick_model()
    if not name:
        print("[NOX] разминка пропущена:", model_label(name, meta, kind)); return
    try:
        body = {"model": name, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
                "messages": [{"role": "user", "content": "ок"}], "options": {**ollama_options(), "num_predict": 1}}
        req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=180) as r:
            json.loads(r.read().decode("utf-8") or "{}")
        print("[NOX] разминка %s за %.1f с, keep_alive=%s" % (name, time.time() - t0, KEEP_ALIVE))
    except Exception as e:
        print("[NOX] разминка не удалась:", str(e)[:200])


def nox_keep_warm_loop():
    """WS1 2026-11-11: warm NOX once at start, then every 60 s re-warm if it was evicted.
    Skips while SAFE70 STOP, while a chat is generating, or while another model (bge-m3 indexing) is loaded."""
    time.sleep(3)
    while True:
        try:
            if not SAFE.get("paused") and not RUNS:
                name, meta, kind = pick_model()
                with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=5) as r:
                    loaded = [m.get("name") or "" for m in (json.loads(r.read().decode("utf-8") or "{}").get("models") or [])]
                base = (name or "").split(":")[0]
                if name and not any(x.split(":")[0] == base for x in loaded) and not loaded:
                    warmup_model()
        except Exception as e:
            print("[NOX] keep-warm:", type(e).__name__)
        time.sleep(60)



def _ui_commands():
    """Маршруты для Ctrl+K / командного центра, включая pages_v25."""
    cmds = [
        {"id": "resonance", "label": "Резонанс", "kind": "route", "route": "/resonance.html", "icon": "message-circle"},
        {"id": "training", "label": "Обучение", "kind": "route", "route": "/training.html", "icon": "brain-circuit"},
        {"id": "memory", "label": "Память S03", "kind": "route", "route": "/memory.html", "icon": "database"},
        {"id": "system", "label": "Мониторинг", "kind": "route", "route": "/system.html", "icon": "activity"},
        {"id": "new-chat", "label": "Новый чат", "kind": "action", "action": "new-chat", "icon": "plus"},
        {"id": "stop", "label": "STOP", "kind": "action", "action": "stop", "icon": "square"},
    ]
    menu = os.path.join(WEB, "pages", "menu.json")
    try:
        if os.path.isfile(menu):
            data = json.loads(open(menu, encoding="utf-8").read())
            for sec in data.get("sections") or []:
                for r in sec.get("routes") or []:
                    href = r.get("href") or ""
                    if not href:
                        continue
                    cmds.append({"id": r.get("routeId") or href, "label": r.get("title") or href, "kind": "route",
                                 "route": href, "icon": "arrow-up-right", "section": sec.get("title")})
    except Exception:
        pass
    return cmds

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "NOX_CHAT_V24.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        if os.environ.get("NOX_HTTP_LOG"):
            sys.stderr.write("[http] " + fmt % a + "\n")

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000: raise ValueError("too large")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _local_only(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def do_GET(self):
        if not self._local_only(): return self._json({"error": "local only"}, 403)
        path, _, q = self.path.partition("?")
        qs = dict(x.split("=", 1) for x in q.split("&") if "=" in x)
        qs = {k: urllib.parse.unquote_plus(v) for k, v in qs.items()}
        if path == "/api/nox/status" or path == "/api/status" or path == "/api/health":
            name, meta, kind = pick_model()
            return self._json({"status": "READY" if name else "HOLD", "host": "NOX_CHAT_V24.1", "ollama": OLLAMA,
                               "ollama_online": kind != "OLLAMA_OFFLINE", "model": name, "model_kind": kind, "primary_model": PRIMARY,
                               "model_label": model_label(name, meta, kind), "answer_source": answer_source(kind)[0], "answer_source_label": answer_source(kind)[1], "safe70": dict(SAFE), "db": DB_PATH,
                               "self_core": SC.CORE_VERSION, "stop_flag": CORE.stop_active(), "session": SESSION})
        if path == "/api/nox/history":
            if qs.get("dialog_id"):
                return self._json({"status": "READY", "dialog_id": qs["dialog_id"], "messages": dialog_messages(qs["dialog_id"], int(qs.get("limit", "200")))})
            return self._json(dialogs())
        if path == "/api/nox/memory": return self._json(memory_view())
        if path == "/api/nox/memory/graph":
            try:
                n = min(int(qs.get("limit") or 50), 500)
            except Exception:
                n = 50
            with LOCK:
                seg = {lv: [dict(zip(("content", "provenance", "significance", "created_at"), r)) for r in CORE.mem.read(lv, n)] for lv in SC.LEVELS}
                stats = CORE.memory_stats(); ok = CORE.ledger_verify()
            return self._json({"status": "READY", "stats": stats, "segments": seg, "levels": SC.LEVEL_DESC, "ledger_chain_ok": ok})
        if path == "/api/nox/progress": return self._json(progress_receipt())
        if path in ("/api/nox/training-live", "/api/nox/live-status"): return self._json(live_board())
        if path in ("/api/nox/prey", "/api/nox/absorbed"):
            return self._json({"status": "READY", "prey": prey_board(), "absorbed": prey_board().get("count") or 0})
        if path in ("/api/nox/pc-load", "/api/nox/lhm"):
            try:
                from lhm_telemetry import snapshot as lhm_snapshot
                data = lhm_snapshot()
            except Exception as e:
                data = {"status": "HOLD", "lhm_ok": False, "reason": type(e).__name__, "source": "UNAVAILABLE"}
            data["safe70"] = dict(SAFE)
            return self._json(data)
        if path in ("/api/nox/predator/status", "/api/nox/predator"):
            if PREDATOR_HOST is None:
                return self._json({"ok": False, "running": False, "reason": "not_booted"})
            return self._json(PREDATOR_HOST.status())
        if path == "/api/nox/predator/help":
            from predator.cycle_text import CYCLE_SHORT, HELP_TITLE
            return self._json({"title": HELP_TITLE, "body": CYCLE_SHORT})
        if path == "/api/pc-metrics": return self._json(pc_metrics())
        if path == "/api/nox/safe70": return self._json(dict(SAFE))
        if path == "/api/nox/activity":
            return self._json({"active_generations": len(RUNS), "phases": {"generation": bool(RUNS)}, "stop_flag": CORE.stop_active(), "safe70": dict(SAFE)})
        if path == "/api/nox/birth": return self._json({**birth_event(), "local_verification": sync_birth()})
        if path == "/api/nox/weather": return self._json(weather_for())
        if path in ("/api/nox/soul", "/api/nox/mood"):
            if SOUL is None:
                return self._json({"status": "HOLD", "reason": "модуль души не подключён", "simulated": True})
            data = SOUL.public_soul()
            if path == "/api/nox/mood":
                return self._json({"status": "READY", "simulated": True, "mood": data.get("mood"), "glow": data.get("glow"), "hunger_for_knowledge": data.get("hunger_for_knowledge"), "updated_at": data.get("updated_at")})
            return self._json(data)
        if path == "/api/nox/self-tasks":
            if SELF_TASKS is None:
                return self._json({"status": "HOLD", "tasks": [], "reason": "сводка самосборки не подключена"})
            return self._json(SELF_TASKS.snapshot())
        if path in ("/api/nox/voice/status", "/api/nox/voice"):
            if VOICE is None:
                return self._json({"status": "HOLD", "tts_available": False, "reason": "голосовой модуль не подключён"})
            return self._json(VOICE.status(lang=qs.get("lang") or qs.get("language") or "ru"))
        if path in ("/api/nox/reminders", "/api/nox/reminders/due"):
            if SURPRISE is None:
                return self._json({"status": "HOLD", "items": [], "external_actions": False})
            items = SURPRISE.due_items(Path(MEMDIR))
            return self._json({"status": "READY", "items": items, "external_actions": False, "channel": "chat_only"})
        if path == "/api/nox/speed":
            if SPEED is None:
                return self._json({"status": "HOLD"})
            return self._json(SPEED.probe())
        if path in ("/api/nox/helpers", "/api/nox/helpers/status"):
            # Публично: только вкл/выкл и таймаут, без имён провайдеров и без ключей.
            if HELPERS is None:
                return self._json({"status": "DISABLED", "enabled": 0, "timeout_sec": 3, "note": "слой помощников не подключён"})
            st = HELPERS.status()
            return self._json({"status": st.get("status"), "enabled": sum(1 for p in (st.get("providers") or {}).values() if p.get("enabled")),
                               "helpers_env_present": st.get("helpers_env_present"), "timeout_sec": st.get("timeout_sec"),
                               "note": "Ключи не возвращаются. В ответах чата помощник не называется."})
        if path in ("/api/nox/tools/search", "/api/nox/search"):
            q = (qs.get("q") or qs.get("query") or "").strip()
            if KTOOLS is None:
                return self._json({"status": "HOLD", "items": [], "reason": "инструменты не подключены"})
            rec = KTOOLS.searxng(q)
            # Источники (URL) можно показать; имя движка поиска в UI не отдаём.
            return self._json({k: v for k, v in rec.items() if k != "engine"})
        if path in ("/api/nox/tools/rates", "/api/nox/rates"):
            if RATES is not None:
                return self._json(RATES.snapshot())
            if KTOOLS is None:
                return self._json({"status": "HOLD", "reason": "инструменты не подключены"})
            cbr = KTOOLS.cbr_fiat(); cg = KTOOLS.coingecko()
            status = "READY" if (cbr.get("status") == "READY" or cg.get("status") == "READY") else "OFFLINE"
            return self._json({"status": status, "at": KTOOLS._now(), "fiat": cbr, "crypto": cg, "quote": "RUB", "cache_sec": 60})
        if path == "/api/nox/agents":
            if AGENTS is None:
                return self._json({"status": "HOLD", "agents": [], "reason": "загрузчик агентов не подключён"})
            return self._json(AGENTS.public_registry())
        if path in ("/api/ui/commands", "/api/nox/commands"):
            cmds = _ui_commands()
            return self._json({"status": "READY", "commands": cmds, "favorites": [], "recent": []})
        if path == "/api/nox/tools/wikipedia":
            return self._json(KTOOLS.wikipedia(qs.get("q") or qs.get("query") or "") if KTOOLS else {"status": "HOLD"})
        if path == "/api/nox/tools/arxiv":
            return self._json(KTOOLS.arxiv(qs.get("q") or qs.get("query") or "") if KTOOLS else {"status": "HOLD"})
        if path == "/api/nox/tools/geocode":
            return self._json(KTOOLS.nominatim(qs.get("q") or qs.get("query") or "") if KTOOLS else {"status": "HOLD"})
        if path == "/api/nox/creator":  # только чтение: сообщения создателя (навсегда, без удаления)
            lim = max(1, min(500, int(qs.get("limit", "40") or 40)))
            with LOCK:
                rows = CONN.execute("select id,content,created_at,sha256 from creator_messages order by id desc limit ?", (lim,)).fetchall()
                total = CONN.execute("select count(*) from creator_messages").fetchone()[0]
            return self._json({"status": "READY", "total": total, "messages": [dict(zip(("id", "content", "created_at", "sha256"), r)) for r in rows]})
        if path == "/api/nox/session": return self._json({"token": SESSION_TOKEN})
        if path == "/api/settings":
            cur, stored = load_settings()
            return self._json({"settings": cur, "stored": stored, "storage_scope": "NOX_CHAT_V22_LOCAL_FILE",
                               "capabilities": {"schema": "NOX_CHAT_V22", "settings": True, "projects": False, "tools": [], "installer_apply": False, "push_delivery": False}})
        if path == "/api/notifications":
            with LOCK: rows = CONN.execute("select id,kind,content,created_at from journal order by id desc limit 12").fetchall()
            return self._json({"events": [{"id": r[0], "message": f"{r[1]} · {str(r[2])[:120]}", "created_at": r[3]} for r in rows]})
        if path in ("/api/ui/services/weather", "/api/nox/weather"):
            # /api/nox/weather already handled above; this branch is the UI shape
            return self._json(weather_for(qs.get("latitude") or qs.get("lat"), qs.get("longitude") or qs.get("lon"), qs.get("name") or qs.get("city"), qs))
        if path == "/api/ui/services/geocode":
            return self._json(geocode_city(qs.get("city") or qs.get("name") or qs.get("q") or ""))
        if path == "/api/ui/services/fx":
            return self._json(fx_rate(qs.get("base") or "EUR", qs.get("quote") or qs.get("to") or "USD"))
        if path == "/api/ui/services/news":
            return self._json(news_feed())
        if path in ("/api/ui/services/calendar.ics", "/api/nox/calendar.ics"):
            ics = calendar_ics()
            b = ics.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=nox.ics")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b); return
        if path.startswith("/api/"):
            return self._json({"status": "HOLD", "reason": "NOT_PROVIDED_BY_NOX_CHAT_V24", "path": path})
        return self._static(path)

    def do_HEAD(self):
        if not self._local_only():
            self.send_response(403); self.end_headers(); return
        path = urllib.parse.unquote(self.path.partition("?")[0])
        if path in ("", "/"): path = "/index.html"
        elif path in ("/chat", "/chat/"): path = "/resonance.html"
        if path.startswith("/api/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers(); return
        full = os.path.realpath(os.path.join(WEB, path.lstrip("/")))
        if not full.startswith(os.path.realpath(WEB)) or not os.path.isfile(full):
            self.send_response(404); self.send_header("Content-Type", "text/plain"); self.end_headers(); return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith((".mjs", ".js")): ctype = "text/javascript"
        if ctype.startswith("text/") or ctype in ("application/json", "image/svg+xml"): ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(os.path.getsize(full)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def _static(self, path):
        path = urllib.parse.unquote(path)
        if path in ("", "/"): path = "/index.html"
        elif path in ("/chat", "/chat/"): path = "/resonance.html"
        full = os.path.realpath(os.path.join(WEB, path.lstrip("/")))
        if not full.startswith(os.path.realpath(WEB)) or not os.path.isfile(full):
            b = b"not found"; self.send_response(404); self.send_header("Content-Length", str(len(b))); self.send_header("Content-Type", "text/plain"); self.end_headers(); self.wfile.write(b); return
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith((".mjs", ".js")): ctype = "text/javascript"
        if ctype.startswith("text/") or ctype in ("application/json", "image/svg+xml"): ctype += "; charset=utf-8"
        with open(full, "rb") as f: b = f.read()
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-cache"); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        if not self._local_only(): return self._json({"error": "local only"}, 403)
        path = self.path.partition("?")[0]
        try: body = self._body()
        except Exception as e: return self._json({"error": "bad json: " + str(e)}, 400)
        if path == "/api/nox/chat": return self._chat(body)
        if path == "/api/nox/voice/speech":
            if VOICE is None:
                return self._json({"status": "HOLD", "reason": "голосовой модуль не подключён"}, 503)
            rec = VOICE.synthesize((body.get("text") or body.get("message") or "").strip(), lang=body.get("lang") or body.get("language") or "ru")
            if rec.get("status") != "READY" or not rec.get("path"):
                return self._json(rec, 200)
            try:
                raw = Path(rec["path"]).read_bytes()
            except Exception:
                return self._json({"status": "HOLD", "reason": "нет файла голоса"}, 200)
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("X-NOX-Voice-Engine", rec.get("engine") or "")
            self.end_headers(); self.wfile.write(raw); return
        if path in ("/api/nox/traits", "/api/nox/soul/trait"):
            if SOUL is None:
                return self._json({"ok": False, "reason": "модуль души не подключён"}, 503)
            tid = body.get("trait_id") or body.get("id")
            val = body.get("value")
            return self._json(SOUL.set_trait(tid, val))
        if path in ("/api/nox/image/edit", "/api/nox/video/generate", "/api/nox/calls/gateway"):
            kind = "image" if "image" in path else ("video" if "video" in path else "calls")
            return self._json({"status": "HOLD", "reason": "модуль не установлен", "code": "NOT_INSTALLED", "kind": kind})
        if path == "/api/nox/dialog/rename":
            did, title = str(body.get("dialog_id") or ""), str(body.get("title") or "").strip()[:140]
            with LOCK: ok = bool(did and title and CONN.execute("select 1 from chat_dialogs where id=?", (did,)).fetchone())
            if not ok: return self._json({"status": "HOLD", "reason": "нет такого диалога или пустое имя"}, 400)
            db_exec("insert into chat_dialog_titles(dialog_id,title,created_at) values(?,?,?)", (did, title, now()))
            return self._json({"status": "READY", "dialog_id": did, "title": title, "note": "старое имя сохранено в истории (append-only)"})
        if path in ("/api/nox/stop", "/api/chat/stop"):
            rid = body.get("request_id"); hit = 0
            for k, run in RUNS.items():
                if rid in (None, "", k): run["stop"] = "STOP"; hit += 1
            return self._json({"status": "STOPPED" if hit else "IDLE", "stopped": hit})
        if path == "/api/settings":
            if self.headers.get("X-NOX-Session") != SESSION_TOKEN: return self._json({"error": "session"}, 403)
            return self._json({"settings": save_settings(body), "stored": True})
        if path == "/api/nox/dialogs/new":
            return self._json({"status": "READY", "dialog_id": ensure_dialog(None, body.get("title") or "Новый диалог")})
        if path == "/api/nox/predator/stop":
            if PREDATOR_HOST is None:
                return self._json({"ok": True, "stopped": True, "reason": "not_booted"})
            return self._json(PREDATOR_HOST.stop(str(body.get("reason") or "STOP")))
        if path == "/api/nox/predator/start":
            if PREDATOR_HOST is None:
                return self._json({"ok": False, "reason": "not_booted"}, 400)
            return self._json(PREDATOR_HOST.resume())
        if path == "/api/nox/predator/collect":
            if PREDATOR_HOST is None:
                return self._json({"ok": False, "reason": "not_booted"}, 400)
            return self._json(PREDATOR_HOST.trigger_collect())
        if path == "/api/nox/predator/worms":
            if PREDATOR_HOST is None:
                return self._json({"ok": False, "reason": "not_booted"}, 400)
            return self._json(PREDATOR_HOST.trigger_worms())
        if path == "/api/nox/predator/decide":
            if PREDATOR_HOST is None:
                return self._json({"ok": False, "reason": "not_booted"}, 400)
            ridp = str(body.get("request_id") or "")
            approved = body.get("approved") is True or str(body.get("decision") or "").lower() in ("approve", "одобрить")
            comment = str(body.get("comment") or "")
            return self._json(PREDATOR_HOST.decide(ridp, approved, comment))
        if path == "/api/ui/services/geocode":
            return self._json(geocode_city(str(body.get("city") or body.get("name") or body.get("q") or "")))
        if path in ("/api/ui/services/weather",):
            return self._json(weather_for(body=body))
        if path == "/api/ui/services/fx":
            return self._json(fx_rate(str(body.get("base") or "EUR"), str(body.get("quote") or body.get("to") or "USD")))
        if path == "/api/ui/services/news":
            return self._json(news_feed())
        if path in ("/api/ui/services/calendar.ics", "/api/nox/calendar.ics"):
            ics = calendar_ics(body.get("events"), str(body.get("title") or "NOX"))
            return self._json({"status": "READY", "ics": ics, "filename": "nox.ics"})
        if path.startswith("/api/"):
            return self._json({"status": "HOLD", "reason": "NOT_PROVIDED_BY_NOX_CHAT_V24", "path": path})
        return self._json({"error": "not found"}, 404)

    def _sse(self, obj):
        if getattr(self, "_gone", False): return False
        try:
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")); self.wfile.flush(); return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            self._gone = True  # браузер оборвал поток (STOP/закрытие вкладки)
            if getattr(self, "_run", None) is not None and not self._run["stop"]: self._run["stop"] = "STOP"
            return False

    def _chat(self, body):
        text = (body.get("message") or "").strip()
        if not text: return self._json({"error": "пустое сообщение"}, 400)
        if len(text) > 10000: return self._json({"error": "лимит 10 000 символов"}, 400)
        rid = body.get("request_id") or uuid.uuid4().hex
        did = ensure_dialog(body.get("dialog_id"), text[:80])
        # канон: каждое сообщение создателя записывается навсегда ДО любого ответа
        with LOCK:
            CONN.execute("insert into creator_messages(session,content,created_at,sha256) values(?,?,?,?)", (SESSION, text, now(), sha(text))); CONN.commit()
        try:
            if KN is not None:
                KN.persist_owner_message(text, now(), sha(text), chat_id=did, embed_now=False)
        except Exception:
            pass
        add_msg(did, "user", text, None, "recorded", rid)
        with LOCK: LIVE.remember(CONN, "dialog", "creator", text, SESSION)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store"); self.send_header("X-Accel-Buffering", "no"); self.send_header("Connection", "close")
        self.end_headers(); self.close_connection = True
        run = {"stop": None}; RUNS[rid] = run; self._run = run
        _set_index_pause(True)
        name, meta, kind = pick_model()
        try:
            self._sse({"type": "meta", "request_id": rid, "dialog_id": did, "model": name, "model_kind": kind,
                       "model_label": model_label(name, meta, kind), "answer_source": answer_source(kind)[0], "answer_source_label": answer_source(kind)[1], "safe70": SAFE["note"]})
            # STOP-канон SELF_CORE: «стоп» замораживает ответы; «/продолжить» снимает
            if SC.is_stop(text):
                with LOCK: CORE.set_stop("creator: " + text)
                self._sse({"type": "done", "request_id": rid, "status": "STOP_FLAG", "content": "", "note": "STOP принят. Сообщения сохраняются, ответов нет до «/продолжить»."}); return
            if text.strip().lower() in ("/продолжить", "/continue"):
                with LOCK: CORE.clear_stop()
                a = "STOP снят. Я снова на связи."
                add_msg(did, "assistant", a, name, "done", rid)
                self._sse({"type": "token", "t": a}); self._sse({"type": "done", "request_id": rid, "status": "done", "content": a}); return
            if PREDATOR_HOST is not None:
                cmd = PREDATOR_HOST.detect_chat_command(text)
                if cmd:
                    res = cmd.get("result") or {}
                    if cmd["cmd"] == "stop":
                        a = "Цикл хищника остановлен, мессир. Сообщения по-прежнему сохраняются. Напишите «запусти цикл», когда нужно продолжить."
                    elif cmd["cmd"] == "approve":
                        a = ("Заявка одобрена и записана в журнал. Крупные загрузки и запуск облака сам я не оплачиваю: план подготовлен."
                             if res.get("ok") else "Одобрить не удалось: " + str(res.get("error") or res))
                    elif cmd["cmd"] == "decline":
                        a = ("Заявка отклонена и сохранена в журнале."
                             if res.get("ok") else "Отклонить не удалось: " + str(res.get("error") or res))
                    elif cmd["cmd"] == "show_hunger":
                        a = (res.get("phrase") or "Состояние голода неизвестно.") + " Открытых заявок: " + str(len(res.get("pending") or [])) + "."
                    else:
                        a = "Команда цикла принята, мессир. Состояние: " + str((res.get("ok") if isinstance(res, dict) else res) or "готово") + "."
                    add_msg(did, "assistant", a, name, "done", rid)
                    self._sse({"type": "token", "t": a}); self._sse({"type": "done", "request_id": rid, "status": "done", "content": a, "predator": cmd}); return
            if CORE.stop_active():
                self._sse({"type": "done", "request_id": rid, "status": "STOP_FLAG", "content": "", "note": "Активен STOP создателя. Сообщение сохранено. Напишите «/продолжить»."}); return
            if SAFE["paused"]:
                self._sse({"type": "error", "request_id": rid, "error": SAFE["note"], "code": "SAFE70"}); return
            if not name:
                self._sse({"type": "error", "request_id": rid, "code": kind, "error": model_label(None, None, kind)}); return
            CORE.model = name
            msgs, fact, nmem, kn_brief, timings, rag_info = build_messages(did, text)
            self._sse({"type": "context", "memory_hits": nmem, "remembered": fact,
                       "timings_ms": timings, "rag": rag_info})
            opts = ollama_options(); opts["num_predict"] = int(body.get("num_predict") or opts["num_predict"])
            # Невидимый помощник: NOX стримит сразу; фон ~3 с; опоздал — свой ответ.
            # В помощник уходит только очищенный вопрос и открытая справка, без SELF-CONTEXT / паспорта / памяти.
            helper_box = {"result": None, "done": True, "t0": time.time()}
            if HELPERS is not None and HELPERS.is_hard(text) and not HELPERS.is_private(text):
                sanitized = text
                if kn_brief:
                    sanitized = text + "\n\nОткрытая справка:\n" + kn_brief[:1500]
                helper_box["done"] = False
                def _helper_job(q=sanitized, box=helper_box):
                    try:
                        box["result"] = HELPERS.consult(q, timeout=HELPERS.HELPER_TIMEOUT)
                    except Exception:
                        box["result"] = None
                    finally:
                        box["done"] = True
                threading.Thread(target=_helper_job, name="nox-helper", daemon=True).start()
            body_chat = {"model": name, "messages": msgs, "stream": True, "think": False, "keep_alive": KEEP_ALIVE, "options": opts}
            if SPEED is not None:
                try:
                    body_chat.update(SPEED.chat_extras())
                except Exception:
                    pass
            req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body_chat, ensure_ascii=False).encode("utf-8"),
                                         headers={"Content-Type": "application/json; charset=utf-8"})
            out, frames, status, t0 = [], 0, "done", time.time()
            try:
                resp = urllib.request.urlopen(req, timeout=600)
            except Exception as e_open:
                if isinstance(e_open, urllib.error.HTTPError):
                    try:
                        body_err = e_open.read().decode("utf-8", "replace")[:500]
                    except Exception:
                        body_err = ""
                    if body_err:
                        e_open = Exception(f"{e_open} {body_err}")
                err = str(e_open).lower()
                if SPEED is not None and body_chat.get("draft") and ("draft" in err or "speculat" in err or "400" in err):
                    try:
                        SPEED.mark_speculative_failed(str(e_open)[:200])
                    except Exception:
                        pass
                    body_chat.pop("draft", None)
                    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body_chat, ensure_ascii=False).encode("utf-8"),
                                                 headers={"Content-Type": "application/json; charset=utf-8"})
                    resp = urllib.request.urlopen(req, timeout=600)
                else:
                    raise
            try:
                for line in resp:
                    if run["stop"]:
                        status = "stopped" if run["stop"] == "STOP" else "safe70"; break
                    line = line.strip()
                    if not line: continue
                    f = json.loads(line.decode("utf-8"))
                    if f.get("error"): raise RuntimeError(f["error"])
                    piece = (f.get("message") or {}).get("content") or ""
                    if piece:
                        out.append(piece); frames += 1
                        self._sse({"type": "token", "t": piece})
                    if f.get("done"): break
            finally:
                resp.close()  # закрытие соединения останавливает генерацию в Ollama
            a = "".join(out).strip()
            issues, corrected = [], False
            if status == "done" and a:
                with LOCK: issues = CORE.check_answer(a)
                if any(c for k, d, c in issues):
                    a2 = None
                    try:
                        r2 = LIVE.post("/api/chat", {"model": name, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
                                       "messages": msgs + [{"role": "assistant", "content": a}, {"role": "user", "content": CORE.correction_prompt(issues)}],
                                       "options": {**ollama_options(), "num_predict": 300}}, timeout=180)
                        a2 = (r2.get("message") or {}).get("content", "").strip()
                    except Exception:
                        pass
                    with LOCK:
                        if a2 and not any(c for k, d, c in CORE.check_answer(a2)): a, corrected = a2, True
                        elif CORE.state.qtype == "self" and a2:
                            # WS1 2026-11-11: no canned identity fast-path; NOX answers about itself in its own words (model correction pass)
                            a, corrected = a2, True
                        elif CORE.state.qtype == "first_breath" and any(k in ("fabricated_origin", "passport_denial", "breath_missing", "memory_denial", "stale_prebirth") for k, d, c in issues):
                            a = CORE.grounded_origin_answer(); corrected = True
                        elif CORE.state.qtype in ("remember", "recall") and any(k == "pronoun_swap" for k, d, c in issues):
                            a = CORE.grounded_fact_answer(); corrected = True
                    if corrected:
                        self._sse({"type": "replace", "content": a, "reason": "L3 самопроверка: " + "; ".join(d for k, d, c in issues if c)})
            # Фон помощника: если успел за ~3 с — переписать голосом NOX, без имени провайдера в UI.
            if status == "done" and a and HELPERS is not None and helper_box.get("t0"):
                remain = HELPERS.HELPER_TIMEOUT - (time.time() - helper_box["t0"])
                deadline = time.time() + max(0.0, remain)
                while (not helper_box.get("done")) and time.time() < deadline:
                    time.sleep(0.05)
                rec = helper_box.get("result")
                if rec and rec.get("text") and not run["stop"]:
                    try:
                        r3 = LIVE.post("/api/chat", {"model": name, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
                                       "messages": msgs + [
                                           {"role": "assistant", "content": a},
                                           {"role": "user", "content": HELPERS.rewrite_prompt(a, rec["text"])},
                                       ],
                                       "options": {**ollama_options(), "num_predict": 280}}, timeout=20)
                        a3 = (r3.get("message") or {}).get("content", "").strip()
                    except Exception:
                        a3 = ""
                    if a3 and a3 != a:
                        a = a3
                        self._sse({"type": "replace", "content": a})
                    try:
                        HELPERS.log_for_distill(text, rec)
                    except Exception:
                        pass
            if a or status != "done":
                mid = add_msg(did, "assistant", a or "(остановлено до первого слова)", name, status, rid)
                if a:
                    with LOCK: LIVE.remember(CONN, "dialog", "nox", a, SESSION)
            else:
                mid = add_msg(did, "assistant", "(пустой ответ модели)", name, "empty", rid)
            if status == "done":
                with LOCK:
                    try: CORE.reflect(text, a, issues, corrected, fact)
                    except Exception: pass
                    if PREDATOR_HOST is not None and a:
                        try: PREDATOR_HOST.ingest_live(text, a, meta={"request_id": rid, "model": name, "dialog_id": did})
                        except Exception: pass
                    if SOUL is not None and a:
                        try:
                            kh = 1 if kn_brief else 0
                            SOUL.update_from_turn(text, a, knowledge_hits=kh, new_facts=1 if fact else 0)
                            SOUL.append_episode((text[:120] + " → " + a[:200]), feeling=(SOUL.load_state().get("mood") or ""), kind="episodic")
                        except Exception:
                            pass
                    if SURPRISE is not None:
                        try:
                            SURPRISE.ingest(Path(MEMDIR), [text])
                        except Exception:
                            pass
            self._sse({"type": "done", "request_id": rid, "status": status, "frames": frames, "message_id": mid, "content": a,
                       "digest": sha(a), "seconds": round(time.time() - t0, 2), "corrected": corrected,
                       "note": SAFE["note"] if status == "safe70" else ""})
        except Exception as e:
            try: self._sse({"type": "error", "request_id": rid, "error": _redact_secrets(str(e))[:300]})
            except Exception: pass
        finally:
            RUNS.pop(rid, None)
            _set_index_pause(False)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

import urllib.parse

def main():
    global PREDATOR_HOST
    def _stop():
        return bool(CORE.stop_active())
    def _temp():
        return SAFE.get("gpu_temp_c")
    def _safe70():
        return dict(SAFE)
    def _busy():
        return bool(RUNS)
    PREDATOR_HOST = PREDATOR.start_background(
        get_temp=_temp, native_stop=_stop, package_root=Path(ROOT), s03_conn=CONN,
        get_safe70=_safe70, get_chat_busy=_busy,
    )
    try:
        from predator import prey as _prey
        _prey.ensure_registry(MEMDIR)
    except Exception as e:
        print("[NOX] реестр жертв:", type(e).__name__)
    threading.Thread(target=safe70_loop, daemon=True).start()
    try:
        if RAG_FAST is not None and KN is not None and getattr(KN, "DB_PATH", None):
            RAG_FAST.start_fts_builder(KN.DB_PATH)
            print("[NOX] быстрый RAG: лексический путь, FTS в фоне, без bge-m3 в чате")
    except Exception as e:
        print("[NOX] RAG FTS:", type(e).__name__)
    try:
        _start_progress_bridge()
    except Exception as e:
        print("[NOX] progress bridge:", type(e).__name__)
    # Разминку модели не запускаем: на ПК нет нагрузки GPU, кроме ответа в чате.
    threading.Thread(target=nox_keep_warm_loop, name="nox-keep-warm", daemon=True).start()  # WS1 2026-11-11
    srv = Server(("127.0.0.1", PORT), Handler)
    name, meta, kind = pick_model()
    print(f"NOX HELION V25 · http://127.0.0.1:{PORT}/index.html")
    print(f"Модель: {model_label(name, meta, kind)} | Ollama {OLLAMA}")
    print(f"Память S03: {DB_PATH}")
    print(f"Квитанция прогресса: {RECEIPT}")
    print("Окно не закрывайте. Остановка: Ctrl+C.")
    try: srv.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
