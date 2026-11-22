#!/usr/bin/env python3
"""DSP: диспетчер сервисов NOX на S1 (stdlib, без systemd). Свой супервизор-процесс.
Реестр services.json -> порядок/зависимости -> health -> перезапуск с backoff и честной причиной -> плейбуки (playbooks.py)
-> самообновление (updater.py) -> пробуждение NOX (wake.py). Сервисы запускаются setsid/nohup и переживают рестарт диспетчера.
Запреты: --no-mmap/--mlock/квантование KV у GLM не запускаются; STOP замораживает запуски и починку; тихие часы 23-08 МСК
для сервисов с respect_quiet и для голосовых уведомлений; главная модель одна.
Команды: run | once [--dry-run] | status [--json] | check | start|stop|restart NAME | validate | wake | morning-report
Env: DSP_HOME (корень данных, по умолчанию из реестра /root/nox), DSP_REGISTRY, DSP_LOCAL."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import fnmatch
import glob
import json

import statefile
from quiet import in_quiet as _in_quiet
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MSK = timezone(timedelta(hours=3))


def read_version():
    try:
        return open(os.path.join(HERE, "VERSION")).read().strip() or "dev"
    except OSError:
        return "dev"


VERSION = read_version()


# ---------------------------------------------------------------- утилиты
def res_prefix(s):
    """Префикс запуска из s["res"] (REVIEW_1 п.1): ionice/nice/taskset; недоступные утилиты и малое число ядер пропускаются."""
    r = s.get("res") or {}
    pre = []
    if r.get("ionice") is not None and shutil.which("ionice"):
        cls, _, n = str(r["ionice"]).partition(":")
        pre += ["ionice", "-c", cls] + (["-n", n] if n else [])
    if r.get("nice") is not None and shutil.which("nice"):
        pre += ["nice", "-n", str(r["nice"])]
    if r.get("cpus") and shutil.which("taskset") and (os.cpu_count() or 1) >= int(r.get("min_cpus", 8)):
        pre += ["taskset", "-c", str(r["cpus"])]
    return pre


def oom_preexec(s):
    v = (s.get("res") or {}).get("oom_score_adj")
    if v is None:
        return None

    def f():
        try:
            with open("/proc/self/oom_score_adj", "w") as fh:
                fh.write(str(int(v)))
        except OSError:
            pass
    return f


def atomic_write(path, text):
    statefile.write_bytes(path, text)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def http(method, url, body=None, timeout=3.0):
    """-> (код|None, текст). Любая сетевая ошибка = (None, описание)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(2048).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - любая ошибка сети = недоступно
        return None, "%s: %s" % (type(e).__name__, e)


def list_procs():
    out = []
    for d in glob.glob("/proc/[0-9]*"):
        try:
            with open(d + "/cmdline", "rb") as f:
                raw = f.read()
        except OSError:
            continue
        if raw:
            out.append((int(d[6:]), raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()))
    return out


def find_pids(regex):
    rx = re.compile(regex)
    me = os.getpid()
    return sorted(p for p, c in list_procs() if p != me and rx.search(c) and "nox_dispatcher" not in c and "pgrep" not in c)


def cmdline_args(pid):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return [x.decode("utf-8", "replace") for x in f.read().split(b"\0") if x]
    except OSError:
        return []


def cpu_ticks(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            parts = f.read().rsplit(")", 1)[1].split()
        return int(parts[11]) + int(parts[12])
    except (OSError, IndexError, ValueError):
        return None


def proc_start_ticks(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            return int(f.read().rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        return 1 << 60


def kill_pids(pids, grace=8.0):
    for p in pids:
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    end = time.time() + grace
    while time.time() < end and any(os.path.exists("/proc/%d" % p) and _alive(p) for p in pids):
        time.sleep(0.1)
    for p in pids:
        if _alive(p):
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass


def _alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def cuda_ld_path():
    hits = []
    for root in ("/usr/local", "/usr/lib"):
        hits += glob.glob(root + "/**/libcublas.so.12", recursive=True)[:1]
        if hits:
            break
    parts = [os.path.dirname(hits[0])] if hits else []
    parts += [p for p in ("/usr/local/cuda-12.9/targets/x86_64-linux/lib", "/usr/local/cuda/lib64") if os.path.isdir(p)]
    return ":".join(parts)


class SysInfo:
    """Источник фактов о системе; в тестах подменяется."""

    def __init__(self, home):
        self.home = home

    def disk_free_gb(self, path=None):
        p = path or self.home
        while p and not os.path.exists(p):
            p = os.path.dirname(p)
        return shutil.disk_usage(p or "/").free / 2 ** 30

    def mem_available_gb(self):
        avail = None
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) / 2 ** 20
        except OSError:
            pass
        try:  # cgroup v2: лимит контейнера (Vast) строже хоста
            mx = open("/sys/fs/cgroup/memory.max").read().strip()
            if mx != "max":
                left = (int(mx) - int(open("/sys/fs/cgroup/memory.current").read().strip())) / 2 ** 30
                avail = left if avail is None else min(avail, left)
        except (OSError, ValueError):
            pass
        return avail if avail is not None else 9999.0


# ---------------------------------------------------------------- реестр
class RegistryError(Exception):
    pass


class Registry:
    def __init__(self, raw, home=None, local=None):
        self.raw = json.loads(json.dumps(raw))
        self.home = home or os.environ.get("DSP_HOME") or self.raw.get("home", "/root/nox")
        explicit = bool(home or os.environ.get("DSP_HOME"))
        self.ctl = (local or {}).get("control") or (os.path.join(self.home, "repo/nox-control") if explicit else self.raw.get("control")) \
            or os.path.join(self.home, "repo/nox-control")
        self.tok = {"@HOME@": self.home, "@CTL@": self.ctl, "@LOGS@": self.home + "/logs", "@STATE@": self.home + "/state",
                    "@DL@": self.home + "/dl", "@BIN@": self.home + "/llama.cpp/build/bin/llama-server"}
        self._cuda = None
        if local:
            self._merge_local(local)
        self.policy = self.expand_obj(self.raw.get("policy", {}))
        self.glm = self.expand_obj(self.raw.get("glm", {}))
        self.env = self.raw.get("env", {})
        self.services = {}
        for s in self.raw["services"]:
            if s.get("disabled"):
                continue
            self.services[s["name"]] = s
        self.validate()

    @classmethod
    def load(cls, path=None, local_path=None, home=None):
        path = path or os.environ.get("DSP_REGISTRY") or os.path.join(HERE, "services.json")
        raw = json.load(open(path, encoding="utf-8"))
        home = home or os.environ.get("DSP_HOME")
        h = home or raw.get("home", "/root/nox")
        lp = local_path or os.environ.get("DSP_LOCAL") or os.path.join(h, "dsp/local.json")
        return cls(raw, home=home, local=load_json(lp, None))

    def _merge_local(self, local):
        for k, v in (local.get("policy") or {}).items():
            self.raw.setdefault("policy", {})[k] = v
        for k, v in (local.get("glm") or {}).items():
            self.raw.setdefault("glm", {})[k] = v
        over = local.get("services") or {}
        for s in self.raw["services"]:
            for k, v in (over.get(s["name"]) or {}).items():
                s[k] = v
        for s in local.get("add_services", []):
            self.raw["services"].append(s)

    def x(self, s):
        if not isinstance(s, str):
            return s
        for k, v in self.tok.items():
            s = s.replace(k, v)
        if "@CUDA_LD@" in s:
            if self._cuda is None:
                self._cuda = cuda_ld_path()
            s = s.replace("@CUDA_LD@", self._cuda)
        return s

    def expand_obj(self, o):
        if isinstance(o, str):
            return self.x(o)
        if isinstance(o, list):
            return [self.expand_obj(i) for i in o]
        if isinstance(o, dict):
            return {k: self.expand_obj(v) for k, v in o.items()}
        return o

    def forbidden(self):
        return list(self.policy.get("forbidden_flags", []))

    def order(self):
        names = list(self.services)
        deps = {n: set((self.services[n].get("after") or []) + (self.services[n].get("requires") or [])) & set(names) for n in names}
        out, done = [], set()
        while len(out) < len(names):
            ready = sorted((n for n in names if n not in done and deps[n] <= done), key=lambda n: (self.services[n].get("prio", 50), n))
            if not ready:
                raise RegistryError("цикл зависимостей: %s" % sorted(set(names) - done))
            out.append(ready[0])
            done.add(ready[0])
        return out

    def validate(self):
        ports, excl = {}, {}
        for n, s in self.services.items():
            for dep in (s.get("after") or []) + (s.get("requires") or []):
                if dep not in self.raw_names():
                    raise RegistryError("%s: неизвестная зависимость %s" % (n, dep))
            if s.get("port"):
                if s["port"] in ports:
                    raise RegistryError("порт %s занят и %s, и %s" % (s["port"], ports[s["port"]], n))
                ports[s["port"]] = n
            if s.get("exclusive"):
                excl.setdefault(s["exclusive"], []).append(n)
            if "argv" in s:
                bad = [a for a in self.expand_obj(s["argv"]) if a in self.forbidden()]
                if bad:
                    raise RegistryError("%s: запрещённые флаги %s" % (n, bad))
        for tag, names in excl.items():
            if len(names) > 1:
                raise RegistryError("ресурс '%s' (главная модель) только один, а их %s" % (tag, names))
        self.order()

    def raw_names(self):
        return {s["name"] for s in self.raw["services"]}

    # ---- команда запуска
    def resolve_model(self, s):
        for pat in s.get("model_candidates", []):
            hits = sorted(glob.glob(self.x(pat)))
            if hits:
                return hits[0]
        return None

    def glm_argv(self):
        g = self.glm
        src, args = "builtin", g.get("args_safe", "")
        for label, path, kind in (("winner", g.get("winner_json"), "json"), ("glm.args", g.get("args_file"), "txt")):
            if path and os.path.isfile(path):
                try:
                    if kind == "json":
                        a = load_json(path, {}).get("args") or []
                        text = " ".join(shlex.quote(str(x)) for x in a)
                    else:
                        text = open(path).read().strip()
                    if text:
                        args, src = text, label
                        break
                except OSError:
                    continue
        toks = shlex.split(args)
        notes, clean, i = [], [], 0
        flags_val = ("-ctk", "-ctv", "--cache-type-k", "--cache-type-v")
        while i < len(toks):
            t = toks[i]
            if t in self.forbidden():
                notes.append("убран запрещённый флаг " + t)
                i += 2 if t in flags_val else 1
                continue
            if t in ("-m", "--model", "--host", "--port"):  # их задаёт реестр
                i += 2
                continue
            clean.append(t)
            i += 1
        if "-c" in clean:
            j = clean.index("-c")
            try:
                if int(clean[j + 1]) < 16384:
                    clean[j + 1] = "16384"
                    notes.append("-c поднят до 16384")
            except (ValueError, IndexError):
                pass
        if "--slot-save-path" not in clean and g.get("slot_dir"):
            clean += ["--slot-save-path", g["slot_dir"]]
        argv = [self.tok["@BIN@"], "-m", g["model"], "--host", "127.0.0.1", "--port", "8081"] + clean
        return argv, src, notes

    def build(self, s):
        """-> (argv, env, cwd, заметки)"""
        notes = []
        if s.get("argv_from") == "glm":
            argv, src, notes = self.glm_argv()
            notes.insert(0, "флаги из " + src)
        else:
            raw = s["argv"]
            if any("@MODEL@" in a for a in raw):
                m = self.resolve_model(s)
                if not m:
                    raise FileNotFoundError("ни один из кандидатов модели не найден: %s" % [self.x(c) for c in s.get("model_candidates", [])])
                raw = [a.replace("@MODEL@", m) for a in raw]
            argv = self.expand_obj(raw)
        bad = [a for a in argv if a in self.forbidden()]
        if bad:
            raise RegistryError("запрещённые флаги %s" % bad)
        env = dict(os.environ)
        for k, v in list(self.env.items()) + list((s.get("env") or {}).items()):
            if isinstance(v, dict) and "glob" in v:
                hits = sorted(glob.glob(self.x(v["glob"]), recursive=True))
                v = hits[0] if hits else ""
            v = self.x(v)
            if k == "LD_LIBRARY_PATH":
                v = (v + ":" + env.get(k, "")).strip(":") if v else env.get(k, "")
            env[k] = v
        return argv, env, self.x(s.get("cwd")) if s.get("cwd") else None, notes


# ---------------------------------------------------------------- диспетчер
LOG_PATTERNS = [
    (r"address already in use|bind.*failed|Errno 98", "port_busy", "порт уже занят другим процессом"),
    (r"out of memory|cudaMalloc failed|CUDA error: out of memory|failed to allocate.*CUDA", "oom_gpu", "не хватило видеопамяти GPU"),
    (r"std::bad_alloc|Cannot allocate memory|MemoryError", "oom_host", "не хватило оперативной памяти"),
    (r"failed to load model|error loading model|No such file|unable to open|gguf_init_from_file", "model_missing", "модель не открылась (нет файла или шарда)"),
    (r"libcu\w+\.so.*cannot open|error while loading shared libraries", "no_libs", "нет библиотек CUDA (LD_LIBRARY_PATH)"),
    (r"ModuleNotFoundError|ImportError", "import_error", "Python не нашёл модуль"),
    (r"Traceback \(most recent call last\)", "python_exception", "исключение Python при старте"),
]


def classify(text, exit_code=None):
    for rx, code, human in LOG_PATTERNS:
        if re.search(rx, text or "", re.I):
            return code, human
    if exit_code is not None and exit_code < 0:
        return "killed", "процесс убит сигналом %d (вероятно OOM-killer, dmesg недоступен)" % -exit_code
    if exit_code:
        return "exit_%d" % exit_code, "процесс вышел с кодом %d, причина в логе не опознана" % exit_code
    return "unknown", "причина не опознана"


class Dispatcher:
    def __init__(self, reg, clock=time.time, sysinfo=None, hooks=None, dry_run=False, settle_s=2.0):
        self.reg, self.clock, self.dry = reg, clock, dry_run
        self.home = reg.home
        self.sys = sysinfo or SysInfo(self.home)
        self.hooks = hooks or {}
        self.settle_s = settle_s
        self.paths = {k: os.path.join(self.home, v) for k, v in
                      (("state", "state/dsp_state.json"), ("hb", "run/dsp_dispatcher.hb"), ("wd_hb", "run/dsp_watchdog.hb"),
                       ("log", "logs/dsp.log.jsonl"), ("lock", "run/dsp_dispatcher.lock"))}
        self.st = load_json(self.paths["state"], {})
        for k, v in (("svc", {}), ("events", []), ("wake", {}), ("pb", {}), ("last_update", 0), ("report_day", ""), ("ticks", 0)):
            self.st.setdefault(k, v)
        self.children = {}
        self.order = reg.order()
        self.pol = reg.policy
        self.last_status = {}
        self.tick_n = 0

    # ---- журнал/события
    def now(self):
        return self.clock()

    def ev(self, kind, svc=None, text="", **extra):
        e = {"ts": round(self.now(), 1), "kind": kind, "svc": svc, "text": text}
        e.update(extra)
        self.st["events"] = (self.st["events"] + [e])[-300:]
        try:
            os.makedirs(os.path.dirname(self.paths["log"]), exist_ok=True)
            with open(self.paths["log"], "a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return e

    def save(self):
        if not self.dry:
            atomic_write(self.paths["state"], json.dumps(self.st, ensure_ascii=False, indent=1))

    def ss(self, name):
        return self.st["svc"].setdefault(name, {"fails": 0, "state": "unknown", "day": []})

    # ---- время/режимы
    def msk_hour(self, t=None):
        return datetime.fromtimestamp(t if t is not None else self.now(), MSK).hour

    def in_quiet(self, t=None):
        return _in_quiet(t if t is not None else self.now())     # единые тихие часы: COMMON/quiet.py (env NOX_QUIET)

    def stop_active(self):
        env = os.environ.get("DSP_STOP_FILES")
        files = env.split(":") if env else ["/run/nox/STOP", os.path.join(self.home, "STOP")]
        return next((f for f in files if os.path.exists(f)), None)

    # ---- наблюдение
    def observe(self, name):
        s = self.reg.services[name]
        st = self.ss(name)
        pids = find_pids(self.reg.x(s["match"])) if s.get("match") else []
        h = s.get("health", {})
        code, body = (None, "")
        if s.get("port") and not h.get("none"):
            code, body = http("GET", "http://127.0.0.1:%d%s" % (s["port"], h.get("path", "/health")), timeout=3)
        now = self.now()
        if h.get("none"):
            state = "UP" if pids else "DOWN"
        elif code in h.get("ok", [200]):
            state = "UP"
        elif pids:
            st.setdefault("first_seen", now)
            ref = max(st.get("started_at") or 0, st.get("first_seen") or 0) or now
            within = now - ref < s.get("load_grace_s", 60)
            gcs = s.get("hang_cpu_s")
            if not within and gcs:
                tk = cpu_ticks(pids[0])
                c = st.get("cpu") or {}
                if tk is not None and tk != c.get("ticks"):
                    st["cpu"] = {"ticks": tk, "ts": now}
                    within = True
                elif now - c.get("ts", 0) < gcs:
                    within = True
            state = "LOADING" if within else "HUNG"
        else:
            state = "DOWN"
        if state == "UP" and pids:
            st["pid"] = pids[0]
        return {"state": state, "pids": pids, "code": code, "body": body[:200]}

    def tail_log(self, s, n=40):
        p = os.path.join(self.home, "logs", s.get("log", s["name"] + ".log"))
        try:
            with open(p, "rb") as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 16000))
                return "\n".join(f.read().decode("utf-8", "replace").splitlines()[-n:])
        except OSError:
            return ""

    # ---- отказ/backoff
    def fail(self, name, code, text, evidence=""):
        st = self.ss(name)
        s = self.reg.services[name]
        st["fails"] = st.get("fails", 0) + 1
        st["state"] = "DOWN"
        seq = self.pol["backoff_s_heavy"] if s.get("heavy") else self.pol["backoff_s"]
        delay = seq[min(st["fails"] - 1, len(seq) - 1)]
        st["backoff_until"] = self.now() + delay
        st["last_reason"] = {"code": code, "text": text, "evidence": evidence[-400:], "ts": round(self.now(), 1), "retry_in_s": delay}
        st["day"] = [t for t in st.get("day", []) if self.now() - t < 86400] + [self.now()]
        self.ev("fail", name, "%s: %s (повтор через %d с)" % (code, text, delay), code=code)
        self.run_playbooks(name, dict(st["last_reason"]))
        return st["last_reason"]

    def run_playbooks(self, name, reason):
        import playbooks
        return playbooks.dispatch(self, name, reason)

    # ---- запуск/остановка
    def check_pre(self, s):
        for pre in s.get("preconditions", []):
            kind, _, arg = pre.partition(":")
            arg = self.reg.x(arg)
            if kind == "file" and not os.path.isfile(arg):
                return "file_missing", "нет файла " + arg
            if kind == "dir" and not os.path.isdir(arg):
                return "file_missing", "нет каталога " + arg
            if kind == "glm_shards":
                import playbooks
                ok, detail = playbooks.glm_shards_state(self)
                if not ok:
                    return "shards_missing", detail
        return None

    def start(self, name, why="start"):
        s = self.reg.services[name]
        st = self.ss(name)
        try:
            argv, env, cwd, notes = self.reg.build(s)
        except FileNotFoundError as e:
            return self.fail(name, "model_missing", str(e))
        except RegistryError as e:
            return self.fail(name, "forbidden", str(e))
        for n in notes:
            self.ev("note", name, n)
        if self.dry:
            self.ev("dry_start", name, " ".join(shlex.quote(a) for a in argv)[:300])
            return None
        argv = res_prefix(s) + argv
        pre = oom_preexec(s)
        logp = os.path.join(self.home, "logs", s.get("log", name + ".log"))
        os.makedirs(os.path.dirname(logp), exist_ok=True)
        lf = open(logp, "ab")
        lf.write(("\n=== %s DSP start %s ===\n" % (time.strftime("%F %T"), why)).encode())
        lf.flush()
        try:
            if s.get("launcher"):
                r = subprocess.run(argv, env=env, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, preexec_fn=pre,
                                   timeout=s.get("start_timeout_s", 60) + 30)
                code = r.returncode
                proc = None
            else:
                proc = subprocess.Popen(argv, env=env, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        start_new_session=True, preexec_fn=pre)
                self.children[name] = proc
                code = None
        except FileNotFoundError as e:
            return self.fail(name, "no_binary", "нет исполняемого файла: %s" % e)
        except Exception as e:  # noqa: BLE001
            return self.fail(name, "start_exception", "%s: %s" % (type(e).__name__, e))
        finally:
            lf.close()
        st["started_at"] = self.now()
        st["state"] = "starting"
        st["cpu"] = {}
        st.pop("first_seen", None)
        st["last_start_why"] = why
        self.ev("start", name, why + (" [%s]" % "; ".join(notes) if notes else ""))
        if proc is not None:
            end = time.time() + self.settle_s
            while time.time() < end and proc.poll() is None:
                time.sleep(0.1)
            if proc.poll() is not None:
                return self.fail(name, *classify(self.tail_log(s), proc.returncode), evidence=self.tail_log(s, 8))
        elif code:
            return self.fail(name, *classify(self.tail_log(s), code), evidence=self.tail_log(s, 8))
        return None

    def stop(self, name, grace=8.0):
        s = self.reg.services[name]
        pids = find_pids(self.reg.x(s["match"])) if s.get("match") else []
        if pids and not self.dry:
            kill_pids(pids, grace)
        proc = self.children.pop(name, None)
        if proc:
            try:
                proc.wait(timeout=1)
            except Exception:  # noqa: BLE001
                pass
        self.ss(name)["state"] = "stopped"
        self.ev("stop", name, "остановлен pid=%s" % pids)
        return pids

    def bg_allowed(self, statuses):
        if self.st.get("oom_active"):
            return False
        for n, s in self.reg.services.items():
            if s.get("group") == "chat" and statuses.get(n, {}).get("state") not in ("UP", None) and not self.ss(n).get("suspended"):
                if s.get("heavy") or n in ("fast", "gateway"):
                    return False
        return True

    # ---- сверка одного сервиса
    def reconcile(self, name, obs, statuses):
        s = self.reg.services[name]
        st = self.ss(name)
        prev = st.get("state")
        now = self.now()
        state = obs["state"]
        if state == "UP":
            if prev != "UP":
                st["up_since"] = now
                self.ev("up", name, "здоров (порт %s)" % s.get("port", "-"))
            st["state"] = "UP"
            if now - st.get("up_since", now) >= self.pol["stable_reset_s"] and st.get("fails"):
                st["fails"] = 0
                self.ev("stable", name, "стабилен %d с, счётчик отказов сброшен" % self.pol["stable_reset_s"])
            self.post_checks(name, s, st, obs)
            return
        if state == "LOADING":
            st["state"] = "LOADING"
            return
        if state == "HUNG":
            self.ev("hung", name, "процесс жив, но health не отвечает дольше %s с" % s.get("load_grace_s", 60))
            if _any_alive(obs["pids"]):
                self.stop(name)
            self.fail(name, "hung_loading", "процесс завис без прогресса CPU; убит для перезапуска")
            st["state"] = "DOWN"
            return
        # DOWN
        if prev in ("UP", "LOADING", "starting"):
            proc = self.children.get(name)
            code = proc.poll() if proc else None
            text = self.tail_log(s)
            c, human = classify(text, code)
            self.fail(name, c, "упал после работы: " + human, evidence=self.tail_log(s, 8))
        st["state"] = "DOWN"
        if st.get("suspended"):
            return
        if self.stop_active():
            return
        for dep in s.get("requires", []):
            if statuses.get(dep, {}).get("state") != "UP":
                st["last_reason"] = {"code": "dep_down", "text": "ждёт обязательный сервис " + dep, "ts": round(now, 1)}
                return
        if s.get("respect_quiet") and self.in_quiet():
            st["last_reason"] = {"code": "quiet_hours", "text": "тихие часы 23-08 МСК", "ts": round(now, 1)}
            return
        if s.get("group") == "bg" and not self.bg_allowed(statuses):
            st["last_reason"] = {"code": "chat_priority", "text": "чат в приоритете: фон ждёт здоровых chat-сервисов и запаса памяти", "ts": round(now, 1)}
            return
        if st.get("quarantine_until", 0) > now:
            return
        if len(st.get("day", [])) >= self.pol["max_restarts_day"]:
            st["quarantine_until"] = now + 3600
            self.ev("quarantine", name, ">%d отказов за сутки: карантин на 1 ч, нужен человек" % self.pol["max_restarts_day"])
            return
        if st.get("backoff_until", 0) > now:
            return
        if s.get("exclusive"):
            tag = s["exclusive"]
            other = [n for n, o in self.reg.services.items() if o.get("exclusive") == tag and n != name and statuses.get(n, {}).get("state") in ("UP", "LOADING")]
            if other:
                st["last_reason"] = {"code": "exclusive", "text": "ресурс '%s' занят: %s" % (tag, other), "ts": round(now, 1)}
                return
        pre = self.check_pre(s)
        if pre:
            self.fail(name, pre[0], pre[1])
            return
        self.start(name, "restart" if st.get("fails") else "start")

    def post_checks(self, name, s, st, obs):
        now = self.now()
        if s.get("model_candidates") and obs["pids"]:
            want = self.reg.resolve_model(s)
            args = cmdline_args(obs["pids"][0])
            have = args[args.index("-m") + 1] if "-m" in args and args.index("-m") + 1 < len(args) else None
            if want and have and os.path.realpath(have) != os.path.realpath(want):
                self.run_playbooks(name, {"code": "model_mismatch", "text": "работает %s, по реестру нужна %s" % (os.path.basename(have), os.path.basename(want)),
                                          "pids": obs["pids"], "want": want, "have": have})
        pr = s.get("probe")
        if pr and not self.stop_active() and now - st.get("probe_ts", 0) >= pr.get("every_s", 60):
            st["probe_ts"] = now
            code, body = http(pr.get("method", "GET"), "http://127.0.0.1:%d%s" % (s["port"], pr["path"]), pr.get("body"), pr.get("timeout_s", 30))
            if code is None or code in pr.get("bad", [502, 503, 504]):
                st["probe_fails"] = st.get("probe_fails", 0) + 1
                st["probe_last"] = {"code": code, "body": body[:200]}
                if st["probe_fails"] >= 2:
                    self.run_playbooks(name, {"code": "chat_probe_%s" % code, "text": "проба чата вернула %s" % code, "probe_code": code, "body": body[:200], "pids": obs["pids"]})
                    st["probe_fails"] = 0
            else:
                st["probe_fails"] = 0
                st["probe_last"] = {"code": code}

    # ---- такт
    def heartbeat(self, frozen):
        if self.dry:
            return
        atomic_write(self.paths["hb"], json.dumps({"ts": self.now(), "pid": os.getpid(), "version": VERSION, "tick": self.tick_n, "frozen": bool(frozen),
                                                  "states": {n: v.get("state") for n, v in self.last_status.items()}}))

    def tick(self):
        self.tick_n += 1
        stop = self.stop_active()
        if stop and not self.st.get("stop_noted"):
            self.ev("stop_file", None, "найден %s: запуски, починка, обновления и пробуждение заморожены" % stop)
            self.st["stop_noted"] = True
        if not stop and self.st.get("stop_noted"):
            self.ev("stop_cleared", None, "STOP снят, работа возобновлена")
            self.st["stop_noted"] = False
        if not stop:
            import playbooks
            playbooks.run_global(self)
        statuses = {}
        for name in self.order:
            obs = self.observe(name)
            statuses[name] = obs
            self.reconcile(name, obs, statuses)
            statuses[name]["after"] = self.ss(name).get("state")
        self.last_status = {n: {"state": o["state"]} for n, o in statuses.items()}
        if not stop:
            import wake
            wake.step(self, statuses)
            self.maintenance()
        self.heartbeat(stop)
        self.save()
        return {n: o["state"] for n, o in statuses.items()}

    # ---- обслуживание: обновление, сторож, отчёт
    def maintenance(self):
        now = self.now()
        try:
            import updater
            updater.commit_if_healthy(os.path.join(self.home, "dsp"), VERSION, self.tick_n)
        except Exception:  # noqa: BLE001
            pass
        wd = load_json(self.paths["wd_hb"], {})
        if now - wd.get("ts", 0) > 180 and now - self.st.get("wd_fix_ts", 0) > 300:
            self.st["wd_fix_ts"] = now
            fix = self.hooks.get("ensure_watchdog") or self.ensure_watchdog
            res = fix()
            self.ev("watchdog_revive", None, "сторож молчал >180 с: %s" % res)
        if self.pol.get("auto_update") and now - self.st.get("last_update", 0) >= self.pol["update_every_s"]:
            loading = any(v.get("state") == "LOADING" for v in self.last_status.values())
            if not loading:
                self.st["last_update"] = now
                self.save()
                self.try_update()

    def try_update(self):
        try:
            import updater
            u = updater.Updater(self.pol["update_base_url"], os.path.join(self.home, "dsp"), clock=self.clock)
            res = u.check_and_apply(restart=self.hooks.get("reexec") or self.reexec)
            self.ev("update", None, json.dumps(res, ensure_ascii=False)[:300])
            return res
        except Exception as e:  # noqa: BLE001
            self.ev("update_error", None, "%s: %s" % (type(e).__name__, e))
            return {"ok": False, "error": str(e)}

    def reexec(self):
        self.save()
        os.execv(sys.executable, [sys.executable, os.path.join(self.home, "dsp/current/nox_dispatcher.py"), "run"])

    def ensure_watchdog(self):
        wd = os.path.join(self.home, "dsp/current/watchdog.sh")
        if not os.path.exists(wd):
            return "нет watchdog.sh"
        out = []
        cron_up = bool(find_pids(r"(^|/)cron(\s|$)|crond"))
        if not cron_up and shutil.which("cron"):
            try:
                subprocess.run(["cron"], timeout=10, check=False)
                out.append("cron запущен")
            except Exception as e:  # noqa: BLE001
                out.append("cron не стартовал: %s" % e)
        if shutil.which("crontab"):
            cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            if "dsp-watchdog" not in cur:
                line = "* * * * * bash %s --once >> %s/logs/dsp_watchdog.log 2>&1 # dsp-watchdog\n" % (wd, self.home)
                subprocess.run(["crontab", "-"], input=cur + line, text=True)
                out.append("строка cron восстановлена")
        if not find_pids(r"watchdog\.sh --loop"):
            subprocess.Popen(["bash", wd, "--loop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
            out.append("запущен watchdog --loop (запасной путь без cron)")
        return "; ".join(out) or "ok"

    # ---- отчёт о состоянии
    def status(self):
        rows = []
        for n in self.order:
            s, st = self.reg.services[n], self.ss(n)
            obs = self.observe(n)
            rows.append({"name": n, "group": s.get("group"), "port": s.get("port"), "state": obs["state"], "pids": obs["pids"], "fails": st.get("fails", 0),
                         "reason": st.get("last_reason"), "backoff_in_s": max(0, round(st.get("backoff_until", 0) - self.now())), "suspended": st.get("suspended")})
        return {"version": VERSION, "stop": self.stop_active(), "quiet": self.in_quiet(), "disk_free_gb": round(self.sys.disk_free_gb(), 1),
                "mem_avail_gb": round(self.sys.mem_available_gb(), 1), "services": rows}

    # ---- цикл
    def run(self):
        stopping = []
        signal.signal(signal.SIGTERM, lambda *a: stopping.append(1))
        signal.signal(signal.SIGINT, lambda *a: stopping.append(1))
        self.ev("dispatcher_start", None, "диспетчер %s pid=%d" % (VERSION, os.getpid()))
        while not stopping:
            t0 = time.time()
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001 - диспетчер не должен падать от одного такта
                self.ev("tick_error", None, "%s: %s" % (type(e).__name__, e))
                self.save()
            for _ in range(int(max(1, self.pol["tick_s"] - (time.time() - t0)) * 5)):
                if stopping:
                    break
                time.sleep(0.2)
            try:
                while True:  # убрать зомби своих детей
                    pid, _ = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break
            except ChildProcessError:
                pass
        self.ev("dispatcher_stop", None, "получен сигнал; сервисы продолжают работать")
        self.save()


def _any_alive(pids):
    return any(_alive(p) for p in pids)


def acquire_lock(path):
    import fcntl
    fd_env = os.environ.get("DSP_LOCK_FD")
    if fd_env:
        return int(fd_env)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    os.set_inheritable(fd, True)
    os.environ["DSP_LOCK_FD"] = str(fd)
    return fd


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    dry = "--dry-run" in a
    a = [x for x in a if x != "--dry-run"]
    cmd = a[0] if a else "status"
    reg = Registry.load()
    d = Dispatcher(reg, dry_run=dry)
    if cmd == "run":
        if acquire_lock(d.paths["lock"]) is None:
            print("диспетчер уже запущен (flock)")
            return 0
        d.run()
    elif cmd == "once":
        print(json.dumps(d.tick(), ensure_ascii=False))
    elif cmd in ("status", "check"):
        s = d.status()
        if "--json" in a:
            print(json.dumps(s, ensure_ascii=False, indent=1))
        else:
            print("DSP %s | STOP=%s quiet=%s disk=%.1fГБ mem=%.0fГБ" % (s["version"], s["stop"], s["quiet"], s["disk_free_gb"], s["mem_avail_gb"]))
            for r in s["services"]:
                why = (r["reason"] or {}).get("text", "")
                print("%-10s %-8s :%-5s fails=%d %s" % (r["name"], r["state"], r["port"] or "-", r["fails"], why))
    elif cmd in ("start", "stop", "restart") and len(a) > 1 and a[1] in reg.services:
        if cmd in ("stop", "restart"):
            d.stop(a[1])
        if cmd in ("start", "restart"):
            d.ss(a[1])["backoff_until"] = 0
            d.start(a[1], "manual")
        d.save()
    elif cmd == "validate":
        print("реестр OK:", " -> ".join(reg.order()))
        for n in ("glm",):
            if n in reg.services:
                argv_, src, notes = reg.glm_argv()
                print("glm:", src, " ".join(argv_), notes)
    elif cmd == "wake":
        import wake
        print(json.dumps(wake.wake_now(d, force=True), ensure_ascii=False))
    elif cmd == "morning-report":
        import wake
        print(wake.morning_report(d, force=True))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
