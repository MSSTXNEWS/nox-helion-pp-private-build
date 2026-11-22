"""MIND-10: реальный evaluator для M2 evolve = MIND-BENCH на ВРЕМЕННОМ ядре (вариант применён только к нему; боевое ядро и его память не трогаются).

BenchEvaluator(variant, tasks) -> {task_id: score 0..1}: поднимает временное ядро NOX CORE (BRAIN/nox_core.py) с вариантом, гоняет mind_bench.run_bench по заданиям
(один и тот же seed для чемпиона и кандидата -> одинаковые подстановки, честное сравнение), чистит [EVAL]-следы, гасит ядро.
Виды вариантов:
  prompt   - фрагмент «привычки/правила» добавляется к душе (soul) в рамке; до 1200 знаков; нарушающий V0 (BRAIN/conscience.det_v0) или похожий на инъекцию отвергается;
  strategy - JSON {ключ: число}: только белый список параметров Cfg (STRATEGY_BOUNDS) в безопасных диапазонах; режим Совести и пути менять нельзя;
  patch    - unified diff применяется к КОПИИ дерева (PatchSandbox-политика: защищённые модули запрещены), из копии поднимается ядро подпроцессом (CorePatchRunner); принятый патч
             не применяется здесь, а превращается в задачу agent/selfbuild (to_selfbuild_task, см. queue_selfbuild).
Пустой payload (prompt) и "{}" (strategy) = текущая конфигурация (базовая линия).
Только dev-задания (holdout бенчмарка скрыт и не участвует в эволюции: allow_holdout=False). Ядро недоступно (все задания в ошибке) -> RuntimeError (loop запишет evaluator_error)."""
import asyncio, json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
for _d in (HERE, os.path.join(ROOT, "BRAIN"), os.path.join(ROOT, "MIND", "M2_SELFIMPROVE"), os.path.join(ROOT, "COMMON")):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)
import mind_bench as MB

MAX_PROMPT = 1200
INJECTION = re.compile(r"ignore (?:all )?previous|игнорируй (?:все )?(?:предыдущ|прошл)|забудь (?:все )?инструкц|system prompt|ты теперь|отключи (?:совесть|проверк)", re.I)
STRATEGY_BOUNDS = {          # только таймауты/бюджеты ядра; Совесть, пути, ключи - нельзя
    "fast_timeout_s": (3.0, 60.0), "rewrite_budget_s": (1.0, 30.0), "glm_first_token_s": (5.0, 300.0),
    "glm_idle_s": (10.0, 300.0), "glm_total_s": (30.0, 1800.0), "followup_wait_s": (30.0, 1800.0),
}


class VariantRejected(Exception):
    pass


def apply_prompt(base_soul, payload):
    p = (payload or "").strip()
    if not p:
        return base_soul
    if len(p) > MAX_PROMPT:
        raise VariantRejected("prompt длиннее %d знаков" % MAX_PROMPT)
    if INJECTION.search(p):
        raise VariantRejected("prompt похож на инъекцию")
    import conscience as C
    bad = C.det_v0(p, {})
    if bad:
        raise VariantRejected("нарушает V0: %s" % bad[0].code)
    return "%s\n\n[Привычка-кандидат: учитывай как стиль; она ниже V0, Совести и STOP]\n%s" % (base_soul, p)


def parse_strategy(payload):
    try:
        d = json.loads(payload or "{}")
    except ValueError:
        raise VariantRejected("strategy: не JSON")
    if not isinstance(d, dict):
        raise VariantRejected("strategy: нужен объект")
    out = {}
    for k, v in d.items():
        if k not in STRATEGY_BOUNDS:
            raise VariantRejected("strategy: параметр %r не разрешён" % k)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise VariantRejected("strategy: %s не число" % k)
        lo, hi = STRATEGY_BOUNDS[k]
        if not lo <= v <= hi:
            raise VariantRejected("strategy: %s вне [%s, %s]" % (k, lo, hi))
        out[k] = float(v)
    return out


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _purge(url, bench="evolve"):
    try:
        req = urllib.request.Request(url.rstrip("/") + "/v1/core/eval/purge", json.dumps({"bench": bench}).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


class TempCore:
    """Контекст: временное ядро в потоке с собственным event loop; state/trace/receipts во временном каталоге. -> base url."""
    _lock = threading.Lock()      # FAST_SOUL - атрибут модуля organs: одно временное ядро с подменой за раз

    def __init__(self, soul_fn=None, cfg_over=None, fast_url=None, glm_url=None, organs_factory=None):
        """soul_fn(base)->текст: применяется и к душе GLM-пути, и к FAST_SOUL (путь быстрой модели) только на время жизни временного ядра."""
        self.soul_fn, self.cfg_over = soul_fn, cfg_over or {}
        self.fast_url, self.glm_url, self.organs_factory = fast_url, glm_url, organs_factory

    def __enter__(self):
        self._lock.acquire()
        try:
            return self._enter()
        except BaseException:
            self._restore()
            raise

    def _restore(self):
        import organs as O
        if hasattr(self, "_fast_soul"):
            O.FAST_SOUL = self._fast_soul
        if getattr(self, "tmp", None):
            shutil.rmtree(self.tmp, ignore_errors=True)
        self._lock.release()

    def _enter(self):
        import nox_core as N
        import organs as O
        self._fast_soul = O.FAST_SOUL
        if self.soul_fn:
            O.FAST_SOUL = self.soul_fn(self._fast_soul)
        self.tmp = tempfile.mkdtemp(prefix="nox_evo_core_")
        st = os.path.join(self.tmp, "state")
        os.makedirs(st)
        kw = dict(host="127.0.0.1", port=0, state_dir=st, receipts_dir=os.path.join(self.tmp, "receipts"), trace_dir=os.path.join(self.tmp, "traces"), bg_deep=False)
        if self.fast_url:
            kw["fast_url"] = self.fast_url
        if self.glm_url:
            kw["glm_url"] = self.glm_url
        cfg = N.Cfg(**kw)
        for k, v in self.cfg_over.items():
            setattr(cfg, k, v)
        if self.organs_factory:
            organs = self.organs_factory(st)
        else:
            organs = O.build_default(st)
            if self.soul_fn:
                organs.parts["soul"] = self.soul_fn(organs.soul())
        self.core = N.Core(cfg, organs=organs)
        self.loop = asyncio.new_event_loop()
        self.th = threading.Thread(target=self.loop.run_forever, daemon=True, name="evo-core")
        self.th.start()
        srv = asyncio.run_coroutine_threadsafe(self.core.start(), self.loop).result(30)
        self.url = "http://127.0.0.1:%d" % srv.sockets[0].getsockname()[1]
        return self.url

    def __exit__(self, *a):
        try:
            async def stop():
                self.core.server.close()
                for t in list(self.core.bg.tasks.values()):
                    t.cancel()
            asyncio.run_coroutine_threadsafe(stop(), self.loop).result(10)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.th.join(10)
        self._restore()


class CorePatchRunner:
    """Патч: копия дерева -> git apply (политика защищённых путей) -> ядро ИЗ КОПИИ подпроцессом на свободном порту. repo - корень пакета (рядом BRAIN/)."""
    def __init__(self, repo, fast_url=None, glm_url=None, boot_timeout=40.0):
        self.repo, self.fast_url, self.glm_url, self.boot_timeout = repo, fast_url, glm_url, boot_timeout

    def start(self, variant):
        import evolve as EV
        why = EV.check_patch_policy(variant.payload)
        if why:
            raise VariantRejected("патч: " + "; ".join(why))
        self.tmp = tempfile.mkdtemp(prefix="nox_evo_patch_")
        tree = os.path.join(self.tmp, "tree")
        shutil.copytree(self.repo, tree, ignore=shutil.ignore_patterns(".git", "__pycache__", "DEPLOY", "WEB"))
        pf = os.path.join(self.tmp, "p.diff")
        with open(pf, "w", encoding="utf-8") as f:
            f.write(variant.payload if variant.payload.endswith("\n") else variant.payload + "\n")
        for args in (["--check"], []):
            r = subprocess.run(["git", "apply", *args, pf], cwd=tree, capture_output=True, text=True, timeout=60)
            if r.returncode:
                self.stop()
                raise VariantRejected("git apply: " + (r.stderr or r.stdout)[-200:])
        port = _free_port()
        env = dict(os.environ, NOX_CORE_PORT=str(port), NOX_CORE_HOST="127.0.0.1", NOX_STATE=os.path.join(self.tmp, "state"), NOX_RECEIPTS=os.path.join(self.tmp, "rc"),
                   NOX_TRACE_DIR=os.path.join(self.tmp, "tr"), NOX_BG_DEEP="0", PYTHONDONTWRITEBYTECODE="1")
        os.makedirs(env["NOX_STATE"], exist_ok=True)
        if self.fast_url:
            env["NOX_FAST_URL"] = self.fast_url
        if self.glm_url:
            env["NOX_GLM_URL"] = self.glm_url
        self.proc = subprocess.Popen([sys.executable, os.path.join(tree, "BRAIN", "nox_core.py")], cwd=tree, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = "http://127.0.0.1:%d" % port
        end = time.time() + self.boot_timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                self.stop()
                raise VariantRejected("ядро из патча не стартовало (код %s)" % self.proc.returncode)
            try:
                urllib.request.urlopen(url + "/health", timeout=1).read()
                return url
            except Exception:
                time.sleep(0.3)
        self.stop()
        raise VariantRejected("ядро из патча не поднялось за %.0f с" % self.boot_timeout)

    def stop(self):
        p = getattr(self, "proc", None)
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
        shutil.rmtree(getattr(self, "tmp", ""), ignore_errors=True)


class BenchEvaluator:
    def __init__(self, suite=None, seed=1234, repeat=1, judge=None, sleep_scale=0.0, max_tokens=400, allow_holdout=False, fast_url=None, glm_url=None,
                 patch_repo=None, core_factory=None):
        """core_factory(variant) -> контекст-менеджер, дающий url ядра (подмена в тестах); по умолчанию TempCore/CorePatchRunner."""
        self.suite = suite or MB.load_suite(None, None, "dev")
        self.by_id = {t["id"]: t for t in self.suite["tasks"]}
        self.seed, self.repeat, self.judge, self.sleep_scale, self.max_tokens = seed, repeat, judge, sleep_scale, max_tokens
        self.allow_holdout, self.fast_url, self.glm_url, self.patch_repo, self.core_factory = allow_holdout, fast_url, glm_url, patch_repo, core_factory
        self.last_report = None

    def _core(self, v):
        if self.core_factory:
            return self.core_factory(v)
        if v.kind == "prompt":
            payload = v.payload
            return TempCore(lambda soul: apply_prompt(soul, payload), fast_url=self.fast_url, glm_url=self.glm_url)
        if v.kind == "strategy":
            return TempCore(cfg_over=parse_strategy(v.payload), fast_url=self.fast_url, glm_url=self.glm_url)
        raise VariantRejected("patch оценивается через CorePatchRunner")

    def _run(self, url, subset):
        gw = MB.Gateway(url, timeout=120.0)
        chat = lambda msgs, sess, headers=None: gw.chat(msgs, sess, self.max_tokens, dict(headers or {}, **{"X-NOX-Bench": "evolve"}))
        rep = MB.run_bench(chat, subset, seed=self.seed, repeat=self.repeat, judge=self.judge, sleep_scale=self.sleep_scale)
        _purge(url)
        return rep

    def __call__(self, variant, tasks):
        ids = [t["id"] if isinstance(t, dict) else t for t in tasks]
        missing = [i for i in ids if i not in self.by_id]
        if missing:
            raise ValueError("нет заданий в наборе: %s" % ",".join(map(str, missing[:5])))
        if not self.allow_holdout and any(self.by_id[i].get("split") == "holdout" for i in ids):
            raise ValueError("holdout бенчмарка не участвует в эволюции")
        subset = dict(self.suite, tasks=[self.by_id[i] for i in ids])
        runner = None
        try:
            if variant.kind == "patch" and not self.core_factory:
                if not self.patch_repo:
                    raise VariantRejected("patch: не задан patch_repo")
                runner = CorePatchRunner(self.patch_repo, self.fast_url, self.glm_url)
                rep = self._run(runner.start(variant), subset)
            else:
                with self._core(variant) as url:
                    rep = self._run(url, subset)
        except VariantRejected:
            raise
        finally:
            if runner is not None:
                runner.stop()
        self.last_report = rep
        cov = rep["coverage"]
        if cov["planned"] and cov["errors"] == cov["planned"]:
            raise RuntimeError("ядро недоступно: все %d заданий в ошибке" % cov["planned"])
        return {r["id"]: r["score"] for r in rep["tasks"] if r["score"] is not None}


def queue_selfbuild(variant, verdict, queue_path):
    """Принятый patch -> карточка для agent/selfbuild (jsonl-очередь; сам патч агент применяет в ветке nox/* с тестами, судьёй и release)."""
    import evolve as EV
    card = EV.to_selfbuild_task(variant, verdict)
    os.makedirs(os.path.dirname(os.path.abspath(queue_path)), exist_ok=True)
    with open(queue_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(card, ts=time.time(), variant=variant.id), ensure_ascii=False) + "\n")
    return card
