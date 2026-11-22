"""fastq: единственный клиент быстрой модели :8083 с приоритетами (REVIEW_1 п.1, исправление 2).

P0 - вступление/ответ чата (bridge_intro), P1 - сомнение appraisal, P2 - свёртка CTX/мысли inner_loop, P3 - автобиография/лента/черты.
Лимит одновременных обращений = 1 (в процессе: приоритетная очередь; между процессами: flock на слоте).
Фоновые P2-P3 идут ТОЛЬКО когда чат свободен (файл активности старше NOX_CHAT_IDLE_S, 120 с) И слот GLM свободен
(GET :8081/slots, нет is_processing) И нет ожидающих P0/P1; иначе сразу Deferred (не ожидание). P0/P1 ждут не дольше wait.
Использование: fq = get(); text = fq.chat(messages, P2, max_tokens=160);  llm = fq.llm(P1)  -> callable(prompt|messages)->str.
"""
import heapq
import itertools
import json
import os
import re
import threading
import time
import urllib.request

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

P0, P1, P2, P3 = 0, 1, 2, 3
_THINK = re.compile(r"<think>.*?</think>", re.S)


class FastQError(Exception):
    pass


class Deferred(FastQError):
    """Фоновая задача отложена: чат/GLM заняты. Это нормальный исход, не сбой."""


class Busy(FastQError):
    """Не дождались очереди за wait секунд."""


def _get_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post_json(url, body, timeout):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class FastQ:
    def __init__(self, url=None, model=None, activity_file=None, glm_url=None, idle_s=None, slot_file=None,
                 clock=time.time, post=_post_json, get=_get_json):
        self.url = url or os.environ.get("NOX_FAST_URL", "http://127.0.0.1:8083/v1/chat/completions")
        self.model = model or os.environ.get("NOX_FAST_MODEL", "fast")
        st = os.environ.get("NOX_STATE", "/root/nox/state")
        self.activity_file = activity_file or os.environ.get("NOX_CHAT_ACTIVITY", os.path.join(st, "chat_activity"))
        self.glm_slots = (glm_url or os.environ.get("NOX_GLM_URL", "http://127.0.0.1:8081")).rstrip("/") + "/slots"
        self.idle_s = float(idle_s if idle_s is not None else os.environ.get("NOX_CHAT_IDLE_S", 120))
        self.slot_file = slot_file or os.environ.get("NOX_FASTQ_SLOT", os.path.join(st, "fastq.slot"))
        self.clock, self.post, self.get = clock, post, get
        self.cv = threading.Condition()
        self.heap, self.seq, self.running = [], itertools.count(), False
        self.stats = {"done": 0, "deferred": 0, "busy": 0, "by_prio": {}}

    # --- условия для фона ---
    def chat_idle(self):
        try:
            return self.clock() - os.path.getmtime(self.activity_file) >= self.idle_s
        except OSError:
            return True

    def glm_slot_free(self):
        try:
            return not any(s.get("is_processing") for s in self.get(self.glm_slots, 1.0))
        except Exception:
            return True          # проба не удалась: не блокируем (GLM может быть выключен)

    def background_ok(self):
        with self.cv:
            hi_waiting = any(p <= P1 for p, _, _ in self.heap)
        return not hi_waiting and self.chat_idle() and self.glm_slot_free()

    def touch_activity(self):
        try:
            if not os.path.isdir(os.path.dirname(self.activity_file)):
                return                      # нет каталога состояния (тест/dev) - не создаём
            with open(self.activity_file, "a"):
                pass
            os.utime(self.activity_file, None)
        except OSError:
            pass

    # --- слот ---
    def _acquire_proc(self, prio, deadline):
        me = (prio, next(self.seq), threading.get_ident())
        with self.cv:
            heapq.heappush(self.heap, me)
            while True:
                if not self.running and self.heap[0] == me:
                    self.running = True
                    heapq.heappop(self.heap)
                    return
                left = deadline - self.clock()
                if left <= 0:
                    self.heap.remove(me)
                    heapq.heapify(self.heap)
                    self.cv.notify_all()
                    raise Busy("fastq: очередь P%d занята" % prio)
                self.cv.wait(min(left, 0.2))

    def _release_proc(self):
        with self.cv:
            self.running = False
            self.cv.notify_all()

    def _acquire_file(self, deadline):
        if not fcntl or not os.path.isdir(os.path.dirname(self.slot_file) or "."):
            return None                     # нет каталога состояния: лимит 1 держится только внутри процесса
        try:
            fd = os.open(self.slot_file, os.O_CREAT | os.O_RDWR, 0o600)
        except OSError:
            return None
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError:
                if self.clock() >= deadline:
                    os.close(fd)
                    raise Busy("fastq: слот занят другим процессом")
                time.sleep(0.05)

    def chat(self, messages, prio=P3, max_tokens=160, temperature=0.7, timeout=60.0, wait=None, extra=None):
        """-> текст ответа. Исключения: Deferred (фон отложен), Busy (не дождались), FastQError (сбой модели)."""
        if prio >= P2 and not self.background_ok():
            self.stats["deferred"] += 1
            raise Deferred("fastq: чат или слот GLM заняты (P%d)" % prio)
        if prio == P0 and os.environ.get("NOX_FASTQ_TOUCH") == "1":
            self.touch_activity()           # опционально (шлюз сам пишет chat_activity); по умолчанию не трогаем файл активности
        wait = wait if wait is not None else (timeout if prio <= P1 else 5.0)
        deadline = self.clock() + wait
        try:
            self._acquire_proc(prio, deadline)
        except Busy:
            self.stats["busy"] += 1
            raise
        fd = None
        try:
            try:
                fd = self._acquire_file(deadline)
            except Busy:
                self.stats["busy"] += 1
                raise
            body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                    "stream": False, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}
            if extra:
                body.update(extra)
            try:
                d = self.post(self.url, body, timeout)
                out = _THINK.sub("", d["choices"][0]["message"]["content"] or "").strip()
            except Exception as e:
                raise FastQError("fastq: %s: %s" % (type(e).__name__, e))
            self.stats["done"] += 1
            k = "P%d" % prio
            self.stats["by_prio"][k] = self.stats["by_prio"].get(k, 0) + 1
            return out
        finally:
            if fd is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
            self._release_proc()

    async def achat(self, messages, prio=P0, **kw):
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.chat(messages, prio, **kw))

    def llm(self, prio, system="", **defaults):
        """Фабрика callable(prompt_or_messages, max_tokens=None, temperature=None)->str для потребителей со старым интерфейсом llm()."""
        def call(x, max_tokens=None, temperature=None, **kw):
            msgs = x if isinstance(x, list) else ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": x}]
            a = dict(defaults, **kw)
            if max_tokens is not None:
                a["max_tokens"] = max_tokens
            if temperature is not None:
                a["temperature"] = temperature
            return self.chat(msgs, prio, **a)
        return call


_pool = {}


def get(url=None, model=None):
    """Один FastQ на (url, model) в процессе: лимит 1 и приоритеты работают только если все идут через один объект."""
    key = (url, model)
    if key not in _pool:
        _pool[key] = FastQ(url=url, model=model)
    return _pool[key]
