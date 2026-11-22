"""IMG: координация VRAM-окна на S1 (RTX 5060 Ti 16 ГБ, GLM -ngl 24 + быстрый тир Qwen на :8083).

Лестница (останавливаемся на первой ступени, которой хватило):
  A  свободной VRAM уже хватает под выбранный режим выгрузки (nvidia-smi) - окно не нужно;
  B  ждём простоя чата (GLM /slots: is_processing=false, gateway тихий N с) до idle_wait_s - чат в приоритете, мы не отнимаем у него ход;
  C  при простое просим диспетчер освободить быстрый тир: lease-файл + `nox_dispatcher.py stop fast` (~6-8 ГБ); по окончании lease снимается, тир возвращается;
  D  ТОЛЬКО если NOX_IMG_ALLOW_GLM_RESTART=1: временно уменьшить -ngl GLM (glm.args) + restart glm, после - вернуть. Минуты без чата; по умолчанию выключено.
Если окна нет, но свободно >= group_min_mb, генерируем в режиме group-offload (мало VRAM, медленнее). Иначе - честная ошибка vram_unavailable.
Диспетчеру нужна правка в 3 строки (см. dsp_patch.json -> dispatcher_hook): не перезапускать сервисы из leased_names() пока lease жив.
Все внешние эффекты (nvidia-smi, HTTP, CLI) инъектируются - тесты без GPU.
"""
import json, os, subprocess, time, urllib.request

HOME = os.environ.get("NOX_HOME", "/root/nox")
LEASE_FILE = os.environ.get("NOX_VRAM_LEASE", os.path.join(HOME, "state", "vram_lease.json"))


# ------------------------------------------------------------------ lease-файл (его читает диспетчер)
def write_lease(holder, names, ttl_s, path=None, now=None):
    now = time.time() if now is None else now
    p = path or LEASE_FILE
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"holder": holder, "suspend": list(names), "expires_ts": now + ttl_s, "created_ts": now}, f)
    os.replace(tmp, p)


def clear_lease(path=None):
    try:
        os.remove(path or LEASE_FILE)
    except FileNotFoundError:
        pass


def leased_names(path=None, now=None):
    """Для диспетчера: какие сервисы сейчас нельзя перезапускать. Просроченный lease игнорируется (защита от зависшего держателя)."""
    now = time.time() if now is None else now
    try:
        with open(path or LEASE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return set(d.get("suspend", [])) if d.get("expires_ts", 0) > now else set()
    except (OSError, ValueError):
        return set()


# ------------------------------------------------------------------ реальные датчики
def gpu_free_mb():
    """Свободная VRAM GPU0 в МБ либо None (нет nvidia-smi / GPU)."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits", "-i", "0"],
                             capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip().splitlines()[0]) if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _get(url, timeout=1.5):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chat_busy(glm_port=8081, fast_port=8083, state_file=None):
    """True если чат занят: у GLM или быстрого тира есть слот в обработке. Недоступный сервис = не занят."""
    for port in (glm_port, fast_port):
        try:
            slots = _get("http://127.0.0.1:%d/slots" % port)
            if any(isinstance(s, dict) and s.get("is_processing") for s in slots):
                return True
        except Exception:
            continue
    return False


def run_cmd(argv, timeout=120):
    r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-400:]


# ------------------------------------------------------------------ окно
class VramUnavailable(Exception):
    pass


class Window:
    """Результат acquire: сколько VRAM можно занимать, какой режим выгрузки, что нужно вернуть."""
    def __init__(self, budget_mb, mode, steps_taken, restore):
        self.budget_mb, self.mode, self.steps, self._restore, self.released = budget_mb, mode, steps_taken, restore, False

    def info(self):
        return {"budget_mb": self.budget_mb, "mode": self.mode, "steps": self.steps}

    def release(self):
        if self.released:
            return
        self.released = True
        for fn in reversed(self._restore):
            try:
                fn()
            except Exception:
                pass


class VramCoordinator:
    """need: {'full_mb': целиком на GPU, 'model_mb': model-offload (пик по компоненту), 'group_mb': group/leaf offload}."""
    def __init__(self, free_mb=gpu_free_mb, busy=chat_busy, run=run_cmd, sleep=time.sleep, clock=time.time,
                 idle_wait_s=None, window_ttl_s=None, suspend=("fast",), allow_glm_restart=None, lease_path=None, home=HOME):
        self.free_mb, self.busy, self.run, self.sleep, self.clock = free_mb, busy, run, sleep, clock
        env = os.environ.get
        self.idle_wait_s = float(env("NOX_IMG_IDLE_WAIT_S", "90")) if idle_wait_s is None else idle_wait_s
        self.ttl = float(env("NOX_IMG_WINDOW_TTL_S", "600")) if window_ttl_s is None else window_ttl_s
        self.suspend = tuple(suspend)
        self.allow_glm_restart = (env("NOX_IMG_ALLOW_GLM_RESTART") == "1") if allow_glm_restart is None else allow_glm_restart
        self.lease_path, self.home = lease_path, home
        self.dsp = env("NOX_DSP_CLI", "python3 %s/dsp/current/nox_dispatcher.py" % home).split()
        self.margin_mb = int(env("NOX_IMG_VRAM_MARGIN_MB", "768"))

    def _pick(self, free, need):
        """Лучший режим, который влезает в free (с запасом)."""
        f = (free or 0) - self.margin_mb
        for mode, key in (("gpu", "full_mb"), ("model", "model_mb"), ("group", "group_mb")):
            if key in need and f >= need[key]:
                return mode, need[key]
        return None, 0

    def acquire(self, need, cancel=None):
        steps, restore = [], []
        free = self.free_mb()
        if free is None:
            # GPU не виден (CPU-режим/нет драйвера): не блокируем, режим group безопасен
            return Window(0, "cpu_or_unknown", ["no_gpu_info"], [])
        mode, bud = self._pick(free, need)
        steps.append("A free=%dMB" % free)
        if mode == "gpu":
            return Window(bud, mode, steps, restore)
        # B: простой чата
        t0 = self.clock()
        while self.busy() and self.clock() - t0 < self.idle_wait_s:
            if cancel is not None and cancel.is_set():
                raise VramUnavailable("отменено при ожидании простоя чата")
            self.sleep(1.0)
        idle = not self.busy()
        steps.append("B chat_idle=%s waited=%.0fs" % (idle, self.clock() - t0))
        if idle and mode != "gpu":
            # C: освободить быстрый тир
            write_lease("img", self.suspend, self.ttl, self.lease_path, self.clock())
            restore.append(lambda: clear_lease(self.lease_path))
            for n in self.suspend:
                rc, out = self.run(self.dsp + ["stop", n])
                steps.append("C stop %s rc=%s" % (n, rc))
                if rc != 0:
                    break
            self.sleep(1.5)
            free2 = self.free_mb()
            if free2 is not None:
                free = free2
                mode, bud = self._pick(free, need)
                steps.append("C free=%dMB" % free)
            if mode != "gpu" and idle and self.allow_glm_restart:
                free, mode, bud = self._glm_ngl_window(need, steps, restore, free)
        if mode is None:
            for fn in reversed(restore):
                fn()
            raise VramUnavailable("VRAM нет: свободно %s МБ, нужно минимум %s МБ (group). Шаги: %s" % (free, need.get("group_mb"), "; ".join(steps)))
        # ранее остановленный тир вернуть по release (диспетчер перезапустит по снятому lease; на всякий случай start)
        if any(s.startswith("C stop") for s in steps):
            restore.insert(0, lambda: [self.run(self.dsp + ["start", n]) for n in self.suspend])
        return Window(bud, mode, steps, restore)

    def _glm_ngl_window(self, need, steps, restore, free):
        """D: -ngl GLM вниз через glm.args + restart glm. Очень дорого (чат недоступен минуты) - только по явному разрешению."""
        args_path = os.path.join(self.home, "gpu_tier", "glm.args")
        try:
            with open(args_path, encoding="utf-8") as f:
                orig = f.read()
        except OSError:
            steps.append("D нет glm.args")
            return free, None, 0
        import re
        m = re.search(r"-ngl\s+(\d+)", orig)
        if not m:
            steps.append("D нет -ngl в glm.args")
            return free, None, 0
        low = max(0, int(m.group(1)) - int(os.environ.get("NOX_IMG_GLM_NGL_DROP", "8")))
        with open(args_path, "w", encoding="utf-8") as f:
            f.write(re.sub(r"-ngl\s+\d+", "-ngl %d" % low, orig, count=1))

        def back():
            with open(args_path, "w", encoding="utf-8") as f:
                f.write(orig)
            self.run(self.dsp + ["restart", "glm"], timeout=600)
        restore.insert(0, back)
        rc, _ = self.run(self.dsp + ["restart", "glm"], timeout=600)
        steps.append("D ngl %s->%d restart rc=%s" % (m.group(1), low, rc))
        self.sleep(2)
        free = self.free_mb()
        mode, bud = self._pick(free, need)
        return free, mode, bud
