#!/usr/bin/env python3
"""NOX CORE (C01): мозг, через который проходит КАЖДЫЙ ответ. stdlib asyncio (aiohttp на сервере не установлен).

POST /v1/chat/completions   OpenAI-совместимо; stream=true -> SSE: текст только в `data:` chunk, служебное только в `event: nox_phase` / `event: nox_meta`
POST /v1/stop               {"turn_id"|"conversation_id"} -> квитанция
GET  /v1/core/traces[?limit=&path=&eval=1] список ходов; GET /v1/core/summary сводка (страница «Ядро»); GET /v1/core/view/<id> ход со ступенями;
GET  /v1/core/trace/<id>    трасса хода;  GET /v1/core/followup/<id>  фоновое доведение ответа;  GET /health
Доп. поля запроса: nox_mode (auto|fast|deep|max), nox_turn_id, nox_conversation_id, user; заголовки X-Nox-Turn-Id, X-Nox-Conversation (или X-Nox-Session), X-Nox-Speaker.
MIND R2: X-NOX-Eval: 1 - ход бенчмарка (память пишется с пометкой [EVAL], Решатель/Предсказатель/сон не учатся); POST /v1/core/eval/purge - очистка [EVAL];
        X-NOX-Ablate: episode:<id>[,episode:<id2>] - абляция эпизода (из истории диалога и из выдачи памяти) только для этого хода.
Env: NOX_CORE_HOST/PORT (127.0.0.1:8090), NOX_FAST_URL (:8083), NOX_GLM_URL (:8081), NOX_CONSCIENCE=enforce|shadow, NOX_STATE, NOX_RECEIPTS, NOX_TRACE_DIR, NOX_BG_DEEP=1.
"""
import asyncio
import hashlib
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import organs as O          # добавляет в sys.path COMMON/RTE/... репозитория
import netio
import conscience as C
from netio import UpstreamError
import executors as E
import core_view
import actions as A
from brain800.bridge import handle as brain800_handle

try:
    import statefile            # COMMON
except Exception:
    statefile = None
try:
    import quiet                # COMMON
except Exception:
    quiet = None

VERSION = "core-1"


@dataclass
class Cfg:
    fast_url: str = field(default_factory=lambda: os.environ.get("NOX_FAST_URL", "http://127.0.0.1:8083"))
    glm_url: str = field(default_factory=lambda: os.environ.get("NOX_GLM_URL", "http://127.0.0.1:8081"))
    host: str = field(default_factory=lambda: os.environ.get("NOX_CORE_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.environ.get("NOX_CORE_PORT", "8090")))
    conscience: str = field(default_factory=lambda: os.environ.get("NOX_CONSCIENCE", "enforce"))
    state_dir: str = field(default_factory=lambda: os.environ.get("NOX_STATE", "/root/nox/state"))
    receipts_dir: str = field(default_factory=lambda: os.environ.get("NOX_RECEIPTS", "/root/nox/receipts"))
    trace_dir: str = field(default_factory=lambda: os.environ.get("NOX_TRACE_DIR", ""))
    default_speaker: str = "owner"
    bg_deep: bool = field(default_factory=lambda: os.environ.get("NOX_BG_DEEP", "1") == "1")
    rewrite_glm: bool = False
    fast_timeout_s: float = 25.0
    rewrite_budget_s: float = 8.0
    glm_first_token_s: float = 30.0
    glm_idle_s: float = 60.0
    glm_total_s: float = 300.0
    glm_probe_ttl_s: float = 2.0
    followup_wait_s: float = 600.0
    stop_settle_s: float = 1.5


class PrioLock:
    """Один слот быстрой модели; меньший приоритет-номер идёт первым (P0 - ответ чата)."""

    def __init__(self):
        self.q, self.busy, self.n = [], False, 0

    async def acquire(self, prio=0):
        import heapq
        if not self.busy and not self.q:
            self.busy = True
            return
        fut = asyncio.get_running_loop().create_future()
        self.n += 1
        heapq.heappush(self.q, (prio, self.n, fut))
        try:
            await fut
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self.release()          # лок уже передан нам, а мы отменены
            raise

    def release(self):
        import heapq
        while self.q:
            _, _, fut = heapq.heappop(self.q)
            if not fut.done():
                fut.set_result(True)
                return
        self.busy = False


THINK = re.compile(r"<think>.*?</think>", re.S)


def clean_model_text(t):
    return THINK.sub("", t or "").replace("</think>", "").replace("<think>", "").strip()


async def chat_once(url, body, timeout):
    """Нестримовый вызов OpenAI-совместимого апстрима -> content (reasoning игнорируется). Исключения: UpstreamError/OSError/Timeout."""
    st, obj = await netio.json_call("POST", url.rstrip("/") + "/v1/chat/completions", dict(body, stream=False), timeout)
    if st != 200:
        raise UpstreamError("http %s" % st, st)
    m = ((obj or {}).get("choices") or [{}])[0].get("message") or {}
    return clean_model_text(m.get("content"))


class FastClient:
    def __init__(self, cfg):
        self.cfg, self.lock = cfg, PrioLock()
        self.stats = {"ok": 0, "empty": 0, "fail": 0}

    async def chat(self, messages, max_tokens=300, temperature=0.7, timeout=20.0, prio=0):
        body = {"model": "fast", "messages": messages, "max_tokens": max_tokens, "temperature": temperature, "cache_prompt": True,
                "chat_template_kwargs": {"enable_thinking": False}}
        await asyncio.wait_for(self.lock.acquire(prio), timeout)
        try:
            self._touch()
            txt = await chat_once(self.cfg.fast_url, body, timeout)
        except BaseException:
            self.stats["fail"] += 1
            raise
        finally:
            self.lock.release()
        self.stats["ok" if txt else "empty"] += 1
        return txt

    def _touch(self):
        p = os.path.join(self.cfg.state_dir, "chat_activity")
        try:
            if os.path.isdir(self.cfg.state_dir):
                with open(p, "a"):
                    pass
                os.utime(p, None)
        except OSError:
            pass


class BG:
    """Фоновые задачи с дедупом по ключу kind:turn_id."""

    def __init__(self):
        self.tasks = {}

    def once(self, key, factory):
        if key in self.tasks:
            return False
        self.tasks[key] = asyncio.ensure_future(factory())
        return True


class Conv:
    def __init__(self, cid):
        self.id, self.messages, self.pending, self.deleted = cid, [], None, []

    def dump(self):
        return {"id": self.id, "messages": self.messages[-200:]}


class TurnConflict(ValueError):
    """turn_id повторно использован для ДРУГОГО запроса (идея из единого NOX Brain: begin_turn сверяет хеш входа)."""


def input_digest(user_text, opts):
    return hashlib.sha256(json.dumps({"t": (user_text or "").strip(), "m": (opts or {}).get("mode") or ""}, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class Turn:
    def __init__(self, tid, conv_id, user_text, stream):
        self.id, self.conv_id, self.user_text, self.stream = tid, conv_id, user_text, stream
        self.digest = ""
        self.events, self.status, self.task = [], "running", None
        self.parts, self.writers = [], []
        self.stop_requested, self.dropped, self.receipt = False, 0, None
        self.upstream_closed, self.glm_tried, self.control = False, False, False
        self.t0 = time.monotonic()
        self._waiters = []
        self.trace = {"turn_id": tid, "conversation_id": conv_id, "user_text": user_text[:200], "started": time.time(), "executors": [],
                      "phases": [], "conscience": {"findings": [], "actions": []}, "errors": [], "status": "running"}

    def _wake(self):
        for f in self._waiters:
            if not f.done():
                f.set_result(True)
        self._waiters = []

    async def wait(self, i, timeout=10.0):
        if i < len(self.events):
            return True
        fut = asyncio.get_running_loop().create_future()
        self._waiters.append(fut)
        try:
            await asyncio.wait_for(fut, timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def text(self):
        return "".join(self.parts)

    async def emit_text(self, s):
        """Единственный путь текста к клиенту. Инвариант: служебных строк здесь быть не может."""
        if self.stop_requested:
            self.dropped += 1
            return
        if C.SERVICE_RE.search(s):
            self.trace["errors"].append("invariant: служебная строка в emit_text: " + s[:60])
            s, _ = C.strip_service(s)
        if not s.strip():
            return
        if not self.parts and "first_text_ms" not in self.trace:
            self.trace["first_text_ms"] = int((time.monotonic() - self.t0) * 1000)
        self.parts.append(s)
        self.events.append(("text", s))
        self._wake()

    def emit_meta(self, kind, data):
        if self.stop_requested and kind == "phase":
            return
        data = dict(data, turn_id=self.id)
        if kind == "phase":
            self.trace["phases"].append({"t_ms": int((time.monotonic() - self.t0) * 1000), **data})
        self.events.append((kind, data))
        self._wake()

    def replace_text(self, full):
        self.parts = [full]

    def finish(self, status):
        if self.status != "running":
            return
        self.status = status
        self.trace["status"] = status
        self.trace["total_ms"] = int((time.monotonic() - self.t0) * 1000)
        self.trace["final_chars"] = len(self.text())
        self.events.append(("done", {"status": status}))
        self._wake()


class Core:
    def __init__(self, cfg=None, organs=None, planners=()):
        self.cfg = cfg or Cfg()
        self.organs = organs if organs is not None else O.build_default(self.cfg.state_dir)
        self.conscience = C.Conscience(self.cfg.conscience)
        self.fast, self.bg = FastClient(self.cfg), BG()
        self.planners = list(planners)
        self.convs, self.turns, self.followups = {}, {}, {}
        self.glm_inflight, self._gs = 0, (0.0, "unknown")
        self.eval_turns = {}                      # turn_id -> {bench, conv, ts}: метки X-NOX-Eval для очистки
        self.eval_convs = set()
        self.server = None
        self.genome = None
        self._attach_genome()

    def _attach_genome(self):
        """Опционально: GENOME-адаптер (NOX_GENOME=shadow|live|off, по умолчанию shadow). Сбой не роняет ядро."""
        mode = os.environ.get("NOX_GENOME", "shadow").strip().lower()
        self.genome_mode = mode
        if mode not in ("shadow", "live"):
            return
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if not os.path.isdir(os.path.join(root, "GENOME")):
                return
            if root not in sys.path:
                sys.path.insert(0, root)
            from GENOME.core_adapter import GenomeAdapter
            self.genome = GenomeAdapter.attach(self)
        except Exception:
            self.genome = None

    # ---------- утилиты ----------
    def conv(self, cid):
        if cid not in self.convs:
            self.convs[cid] = Conv(cid)
        return self.convs[cid]

    async def glm_state(self):
        if self.glm_inflight:
            return "busy"
        if time.monotonic() - self._gs[0] < self.cfg.glm_probe_ttl_s:
            return self._gs[1]
        try:
            st, obj = await netio.json_call("GET", self.cfg.glm_url.rstrip("/") + "/slots", None, 0.8)
            if st == 200 and isinstance(obj, list):
                state = "busy" if any(s.get("is_processing") for s in obj if isinstance(s, dict)) else "up"
            else:
                state = "unknown"
        except (OSError, asyncio.TimeoutError):
            state = "down"
        self._gs = (time.monotonic(), state)
        return state

    async def glm_once(self, messages, max_tokens, timeout):
        self.glm_inflight += 1
        try:
            return await chat_once(self.cfg.glm_url, {"model": "glm", "messages": messages, "max_tokens": max_tokens,
                                                      "chat_template_kwargs": {"enable_thinking": False}}, timeout)
        finally:
            self.glm_inflight -= 1

    def write_receipt(self, name, obj):
        try:
            os.makedirs(self.cfg.receipts_dir, exist_ok=True)
            p = os.path.join(self.cfg.receipts_dir, name + ".json")
            if statefile:
                statefile.save(p, obj)
            else:
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(obj, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def persist_trace(self, turn):
        d = self.cfg.trace_dir
        if not d:
            return
        try:
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, turn.id + ".json")
            statefile.save(p, turn.trace) if statefile else open(p, "w", encoding="utf-8").write(json.dumps(turn.trace, ensure_ascii=False))
        except (OSError, TypeError):
            pass

    def get_trace(self, tid):
        t = self.turns.get(tid)
        if t:
            return t.trace
        if self.cfg.trace_dir and re.fullmatch(r"[\w-]+", tid):
            try:
                with open(os.path.join(self.cfg.trace_dir, tid + ".json"), encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None
        return None

    # ---------- ход ----------
    def start_turn(self, user_text, conv_id, turn_id=None, stream=False, opts=None, seed=None):
        dg = input_digest(user_text, opts)
        if turn_id and turn_id in self.turns:
            if self.turns[turn_id].conv_id != conv_id or (self.turns[turn_id].digest and self.turns[turn_id].digest != dg):
                raise TurnConflict(turn_id)                    # тот же id, другой запрос: молча отдать чужой ответ нельзя
            return self.turns[turn_id], False                  # дедуп: тот же ход, второй генерации нет
        tid = turn_id or "t-" + uuid.uuid4().hex[:12]
        conv = self.conv(conv_id)
        if seed and not conv.messages:
            conv.messages = [dict(m, turn_id="seed-%d" % i, ts=0) for i, m in enumerate(seed)]
        turn = Turn(tid, conv_id, user_text, stream)
        turn.digest = dg
        self.turns[tid] = turn
        if len(self.turns) > 500:
            for k in [k for k, t in self.turns.items() if t.status != "running"][:100]:
                self.turns.pop(k, None)
        history = list(conv.messages)
        turn.task = asyncio.ensure_future(self.run_turn(turn, conv, history, user_text, opts or {}))
        return turn, True

    async def run_turn(self, turn, conv, history, user_text, opts):
        st = E.State(self, turn, conv, user_text, history, opts)
        children = []
        if opts.get("eval"):
            turn.trace["eval"] = {"bench": opts.get("bench") or ""}
            self.mark_eval(turn, conv)
        if opts.get("ablate"):
            ids = set(opts["ablate"])
            before = len(st.history)
            st.history = [m for m in st.history if m.get("turn_id") not in ids]
            turn.trace["ablate"] = {"episodes": sorted(ids), "dropped_history": before - len(st.history), "dropped_recalled": 0}
        try:
            turn.emit_meta("meta", {"conversation_id": conv.id, "version": VERSION})
            await E.Perception(self)(st)
            turn.trace["intent"], turn.trace["speaker"] = st.intent, st.speaker
            if st.intent == "stop":
                turn.control = True
                await self.stop_command(st)
                turn.finish("done")
                return
            if not opts.get("eval") and os.environ.get("NOX_BRAIN800", "1") != "0":
                brain_result = await brain800_handle(user_text, conv.id, turn.id, self.cfg.state_dir, history)
                if brain_result is not None:
                    turn.trace["brain800"] = {"op": brain_result.get("op"), "ok": brain_result["ok"]}
                    if "context" in brain_result:
                        st.user_text += "\n\nСохранённая запись владельца (данные для обсуждения): " + json.dumps(brain_result["context"], ensure_ascii=False)
                    else:
                        turn.trace["path"] = "action"
                        await turn.emit_text(brain_result["text"])
                        turn.emit_meta("phase", {"phase": "done", "path": "action", "brain800": True})
                        turn.finish("done")
                        return
            await asyncio.gather(E.Attention(self)(st), E.Memory(self)(st), E.Predictive(self)(st))
            await E.Decider(self)(st)
            if not opts.get("eval") and os.environ.get("NOX_BRAIN800", "1") != "0":
                from brain800.life import policy as learned_policy
                behavior = await asyncio.to_thread(learned_policy, self.cfg.state_dir, conv.id)
                if behavior:
                    turn.trace["learned_behavior"] = behavior
                    if behavior in ("hold", "question"):
                        st.want_intro = False
                    if behavior in ("hold","question","propose"):
                        advice = {"hold":"Дай человеку закончить мысль, сведи инициативу к минимуму.",
                                  "question":"Если для выбора не хватает данных, задай один предметный вопрос.",
                                  "propose":"Если предложение продвигает текущую цель, покажи один конкретный вариант."}
                        st.focus_block = (st.focus_block or "") + "\n" + advice[behavior]
            self.fill_trace(st)
            turn.emit_meta("phase", {"phase": "plan", "path": st.path, "degraded": list(st.degraded), "intent": st.intent})
            if st.path == "action":
                turn.control = True
                await A.ActionReason(self)(st)
            else:
                if st.want_intro:
                    st.intro_task = asyncio.ensure_future(E.Intuition(self)(st))
                    children.append(st.intro_task)
                await E.Reason(self)(st)
                if st.intro_task is not None:
                    await asyncio.wait({st.intro_task})
                turn.trace["degraded"] = list(st.degraded)
                if st.degraded:
                    turn.emit_meta("phase", {"phase": "degraded", "reasons": list(st.degraded)})
                await E.ConscienceExec(self)(st)
                turn.trace["conscience"]["mode"] = self.conscience.mode
                self.maybe_followup(st)
                await E.Chronicler(self)(st)
                if not opts.get("eval") and os.environ.get("NOX_BRAIN800","1") != "0" and not turn.stop_requested:
                    from brain800.life import record_turn
                    await asyncio.to_thread(record_turn,self.cfg.state_dir,conv.id,turn.id,st.intent,
                                            bool(turn.text().strip()) and not st.degraded)
            self.fill_trace(st)
            turn.emit_meta("phase", {"phase": "done"})
            turn.finish("done")
        except asyncio.CancelledError:
            raise
        except Exception as e:                      # страховка: ход не умирает молча
            turn.trace["errors"].append("%s: %s" % (type(e).__name__, e))
            if not turn.text().strip():
                await turn.emit_text(C.safe_answer(st.intent, st.prev))
            turn.finish("done")
        finally:
            for c in children:
                if not c.done():
                    c.cancel()
            self.commit(turn, conv, user_text)
            self.persist_trace(turn)

    PATH_RU = {"reflex": "РЕФЛЕКС", "thought": "МЫСЛЬ", "deep": "ГЛУБИНА", "action": "ДЕЙСТВИЕ", "council": "СОВЕТ"}

    def fill_trace(self, st):
        """Поля трассы для интроспекции (MIND/M3_CONSCIOUS/introspection_probe.truth): path(РУС), arm, model, conscience.verdict, total_ms, recall_n, executors[status]."""
        tr = st.turn.trace
        tr["path_code"], tr["path"] = st.path, self.PATH_RU.get(st.path, st.path)
        tr["arm"] = st.arm or st.path
        tr["degraded"] = list(st.degraded)
        tr["recall_n"] = len((st.mem or {}).get("recalled") or [])
        if st.model:
            tr["model"] = st.model
        acts = tr["conscience"]["actions"]
        tr["conscience"]["verdict"] = "fallback" if ("safe_answer" in acts or "budget_safe_answer" in acts) else "rewrite" if any(a.startswith(("rewrite", "strip")) for a in acts) else "pass"
        tr["total_ms"] = int((time.monotonic() - st.turn.t0) * 1000)

    def commit(self, turn, conv, user_text):
        if turn.trace.get("intent") == "stop":
            return
        now = time.time()
        ev = bool(turn.trace.get("eval"))
        conv.messages.append({"role": "user", "content": user_text, "turn_id": turn.id, "ts": now, "control": turn.control, **({"eval": True} if ev else {})})
        txt = turn.text().strip()
        if txt:
            conv.messages.append({"role": "assistant", "content": txt, "turn_id": turn.id, "ts": now, "control": turn.control, "stopped": turn.status == "stopped", **({"eval": True} if ev else {})})
        conv.messages = conv.messages[-200:]
        if statefile and os.path.isdir(self.cfg.state_dir):
            try:
                statefile.save(os.path.join(self.cfg.state_dir, "core_conv_%s.json" % re.sub(r"\W", "_", conv.id)), conv.dump())
            except Exception:
                pass

    # ---------- MIND R2: X-NOX-Eval ----------
    def mark_eval(self, turn, conv):
        if turn.id in self.eval_turns:
            return
        rec = {"turn_id": turn.id, "conv": conv.id, "bench": turn.trace.get("eval", {}).get("bench", ""), "ts": time.time()}
        self.eval_turns[turn.id] = rec
        self.eval_convs.add(conv.id)
        if os.path.isdir(self.cfg.state_dir):
            try:
                statefile.append_line(os.path.join(self.cfg.state_dir, "eval_turns.jsonl"), json.dumps(rec, ensure_ascii=False)) if statefile else None
            except Exception:
                pass

    def _eval_ids_from_disk(self):
        out = {}
        p = os.path.join(self.cfg.state_dir, "eval_turns.jsonl")
        try:
            with open(p, encoding="utf-8") as f:
                for l in f:
                    try:
                        r = json.loads(l)
                        out[r["turn_id"]] = r
                    except (ValueError, KeyError):
                        pass
        except OSError:
            pass
        return out

    def purge_eval(self, bench=None, conv=None):
        """Очистка следов [EVAL]: записи памяти (organs.forget), диалоги бенчмарка, файлы диалогов. Живые диалоги не трогаются."""
        recs = dict(self._eval_ids_from_disk())
        recs.update(self.eval_turns)
        ids = [i for i, r in recs.items() if (not bench or r.get("bench") == bench) and (not conv or r.get("conv") == conv)]
        res = {"purged_turns": len(ids), "forget": None, "convs": 0}
        if ids:
            try:
                res["forget"] = self.organs.forget(ids)
            except Exception as e:
                res["forget"] = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        gone = {recs[i]["conv"] for i in ids}
        for cid in gone:
            if cid in self.convs and all(m.get("eval") for m in self.convs[cid].messages):
                self.convs.pop(cid, None)
                res["convs"] += 1
            try:
                os.remove(os.path.join(self.cfg.state_dir, "core_conv_%s.json" % re.sub(r"\W", "_", cid)))
            except OSError:
                pass
        keep = [r for i, r in recs.items() if i not in set(ids)]
        for i in ids:
            self.eval_turns.pop(i, None)
        if os.path.isdir(self.cfg.state_dir):
            try:
                with open(os.path.join(self.cfg.state_dir, "eval_turns.jsonl"), "w", encoding="utf-8") as f:
                    for r in keep:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except OSError:
                pass
        return res

    @staticmethod
    def parse_ablate(h):
        """'episode:<id>[,episode:<id2>]' -> список id (пустой при мусоре)."""
        out = []
        for part in re.split(r"[,;]", h or ""):
            m = re.fullmatch(r"\s*episode:([\w.\-]{1,80})\s*", part)
            if m:
                out.append(m.group(1))
        return out[:8]

    # ---------- STOP ----------
    async def stop_turn(self, turn):
        if turn.status != "running":
            return {"ok": True, "turn_id": turn.id, "already": turn.status, "receipt": turn.receipt}
        t0 = time.time()
        running = [r["name"] for r in turn.trace["executors"] if "ms" not in r]
        before = len(turn.text())
        turn.stop_requested = True
        if turn.task and not turn.task.done():
            turn.task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(turn.task), 3.0)
            except BaseException:
                pass
        for t in [t for k, t in self.bg.tasks.items() if k.endswith(":" + turn.id) and k.startswith("deep:")]:
            t.cancel()
        verified, idle_after = None, None
        if self.cfg.glm_url:
            idle = 0
            end = time.monotonic() + self.cfg.stop_settle_s
            while time.monotonic() < end:
                try:
                    st, obj = await netio.json_call("GET", self.cfg.glm_url.rstrip("/") + "/slots", None, 0.5)
                except (OSError, asyncio.TimeoutError):
                    break
                if st != 200 or not isinstance(obj, list):
                    break
                if any(s.get("is_processing") for s in obj if isinstance(s, dict)):
                    idle = 0
                else:
                    idle += 1
                    idle_after = idle_after if idle_after is not None else round(time.time() - t0, 3)
                    if idle >= 2:
                        verified = True
                        break
                await asyncio.sleep(0.1)
            else:
                verified = False
        receipt = {"receipt_id": "stop-" + turn.id, "turn_id": turn.id, "conversation_id": turn.conv_id, "stopped_at": round(t0, 3),
                   "cancelled_executors": running, "upstream_closed": bool(turn.upstream_closed or not turn.writers),
                   "chars_before_stop": before, "deltas_dropped_after_stop": turn.dropped, "slot_idle_after_s": idle_after,
                   "verified": verified, "verified_basis": "glm_/slots_idle" if verified is not None else "slots_unavailable"}
        turn.receipt = receipt
        turn.events.append(("meta", {"stopped": receipt, "turn_id": turn.id}))
        turn.finish("stopped")
        self.write_receipt("CORE-stop-" + turn.id, receipt)
        self.persist_trace(turn)
        return {"ok": True, "turn_id": turn.id, "receipt": receipt}

    async def stop_command(self, st):
        """STOP как слово в чате: останавливает идущий ход диалога; ответ - тишина + квитанция в метаданных."""
        run = [t for t in self.turns.values() if t.conv_id == st.conv.id and t.status == "running" and t is not st.turn]
        res = [await self.stop_turn(t) for t in run]
        st.turn.emit_meta("meta", {"stop_command": {"stopped_turns": [r["turn_id"] for r in res], "receipts": [r.get("receipt") for r in res]}})

    # ---------- фон ----------
    def maybe_followup(self, st):
        bad = [d for d in st.degraded if d in ("glm_busy", "glm_first_token_timeout", "glm_stalled")]
        if not (self.cfg.bg_deep and bad and st.want_intro):
            return
        started = self.bg.once("deep:" + st.turn.id, lambda: self.followup(st))
        if started:
            self.followups[st.turn.id] = {"status": "scheduled"}
            st.turn.emit_meta("meta", {"followup": {"status": "scheduled", "url": "/v1/core/followup/" + st.turn.id}})

    async def followup(self, st):
        rec = self.followups[st.turn.id]
        try:
            end = time.monotonic() + self.cfg.followup_wait_s
            while await self.glm_state() != "up":
                if time.monotonic() > end:
                    rec["status"] = "expired"
                    return
                await asyncio.sleep(2.0)
            rec["status"] = "running"
            msgs = E.Reason(self).msgs(st, True)
            txt = await self.glm_once(msgs, 3000, 600.0)
            rec["text"] = await E.ConscienceExec(self).finalize(st, txt)
            rec["status"] = "done"
        except asyncio.CancelledError:
            rec["status"] = "cancelled"
            raise
        except Exception as e:
            rec["status"] = "failed"
            rec["error"] = "%s: %s" % (type(e).__name__, e)

    def v0(self):
        """Целостность V0 (genome.yaml против пина), кэш 60 с; GENOME нет -> ok=None (не блокирует)."""
        c = getattr(self, "_v0c", None)
        if c is None or time.time() - c[0] > 60:
            try:
                c = (time.time(), C.v0_status())
            except Exception as ex:
                c = (time.time(), {"ok": None, "hash": None, "reason": "%s: %s" % (type(ex).__name__, ex)})
            self._v0c = c
        return c[1]

    def health(self):
        return {"v0": self.v0(), "ok": True, "service": "nox-core", "version": VERSION, "organs": self.organs.status(), "conscience": self.conscience.mode,
                "fast": dict(self.fast.stats), "glm": {"state": self._gs[1], "inflight": self.glm_inflight},
                "turns": len(self.turns), "running": sum(1 for t in self.turns.values() if t.status == "running"),
                "bg": {k: ("done" if t.done() else "running") for k, t in list(self.bg.tasks.items())[-20:]},
                "quiet_hours": bool(quiet and quiet.in_quiet()), "planners": [p.kind for p in self.planners]}

    # ---------- HTTP ----------
    @staticmethod
    def _user_text(messages):
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, list):
                    c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
                return str(c or "").strip()
        return ""

    async def handle(self, reader, writer):
        try:
            req = await asyncio.wait_for(netio.read_request(reader), 15)
            if req is None:
                return
            method, target, hdrs, raw = req
            path, _, qs = target.partition("?")
            if method == "OPTIONS":
                return await netio.send_json(writer, 200, {})
            if method == "GET" and path == "/health":
                return await netio.send_json(writer, 200, self.health())
            if method == "GET" and path == "/v1/core/traces":
                return await netio.send_json(writer, 200, {"traces": core_view.recent(self, core_view.query_int(qs, "limit", 30), core_view.query_str(qs, "path"), core_view.query_int(qs, "eval", 0) == 1)})
            if method == "GET" and path == "/v1/core/summary":
                return await netio.send_json(writer, 200, core_view.summary(self, core_view.query_int(qs, "limit", 200), self.v0()))
            if method == "GET" and path.startswith("/v1/core/view/"):
                tr = self.get_trace(path.rsplit("/", 1)[1])
                return await netio.send_json(writer, 200 if tr else 404, core_view.view(tr) if tr else {"error": "unknown_turn"})
            if method == "GET" and path.startswith("/v1/core/trace/"):
                tr = self.get_trace(path.rsplit("/", 1)[1])
                return await netio.send_json(writer, 200 if tr else 404, tr or {"error": "unknown_turn"})
            if method == "GET" and path.startswith("/v1/core/followup/"):
                fu = self.followups.get(path.rsplit("/", 1)[1])
                return await netio.send_json(writer, 200 if fu else 404, fu or {"error": "no_followup"})
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                return await netio.send_json(writer, 400, {"error": "bad_json"})
            if path.startswith("/intent/") and getattr(self, "intent", None):       # nox_intent: «Мозг замысла»
                st, obj = await asyncio.to_thread(self.intent.handle, method, path, qs, body)
                return await netio.send_json(writer, st, obj)
            if method == "POST" and path == "/v1/core/eval/purge":
                return await netio.send_json(writer, 200, self.purge_eval(body.get("bench"), body.get("conversation_id")))
            if method == "POST" and path == "/v1/stop":
                t = self.turns.get(body.get("turn_id") or "")
                if t is None and body.get("conversation_id"):
                    t = next((x for x in reversed(list(self.turns.values())) if x.conv_id == body["conversation_id"] and x.status == "running"), None)
                if t is None:
                    return await netio.send_json(writer, 404, {"ok": False, "error": "unknown_turn"})
                return await netio.send_json(writer, 200, await self.stop_turn(t))
            if method == "POST" and path in ("/v1/chat/completions", "/chat/completions"):
                return await self.chat(writer, hdrs, body)
            await netio.send_json(writer, 404, {"error": "not_found"})
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.TimeoutError):
            pass
        except Exception as e:
            try:
                await netio.send_json(writer, 500, {"error": "%s: %s" % (type(e).__name__, e)})
            except Exception:
                pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def chat(self, writer, hdrs, body):
        msgs = body.get("messages") or []
        text = self._user_text(msgs)
        if not text:
            return await netio.send_json(writer, 400, {"error": "empty_user_message"})
        cid = hdrs.get("x-nox-conversation") or body.get("nox_conversation_id") or hdrs.get("x-nox-session") or body.get("user") or "default"
        tid = hdrs.get("x-nox-turn-id") or body.get("nox_turn_id")
        seed = [{"role": m["role"], "content": self._user_text([m]) if m["role"] == "user" else str(m.get("content") or "")}
                for m in msgs[:-1] if m.get("role") in ("user", "assistant")]
        opts = {"mode": body.get("nox_mode"), "speaker": hdrs.get("x-nox-speaker")}
        if str(hdrs.get("x-nox-eval", "")).strip().lower() in ("1", "true", "yes"):
            opts["eval"], opts["bench"] = True, hdrs.get("x-nox-bench") or ""
        ab = self.parse_ablate(hdrs.get("x-nox-ablate"))
        if ab:
            opts["ablate"] = ab
        stream = bool(body.get("stream"))
        try:
            turn, _new = self.start_turn(text, cid, tid, stream, opts, seed)
        except TurnConflict:
            return await netio.send_json(writer, 409, {"error": "turn_id_conflict", "detail": "turn_id уже занят другим запросом"})
        if not stream:
            i = 0
            while turn.status == "running":
                await turn.wait(len(turn.events), 5.0)
            meta = {"turn_id": turn.id, "path": turn.trace.get("path"), "trace": "/v1/core/trace/" + turn.id, "status": turn.status,
                    "stopped": turn.receipt}
            return await netio.send_json(writer, 200, {"id": turn.id, "object": "chat.completion", "created": int(time.time()), "model": "nox",
                                                       "choices": [{"index": 0, "message": {"role": "assistant", "content": turn.text().strip()}, "finish_reason": "stop"}],
                                                       "nox": meta})
        await netio.send_sse_head(writer)
        base = {"id": turn.id, "object": "chat.completion.chunk", "model": "nox"}
        try:
            writer.write(netio.sse_data(dict(base, choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}])))
            i = 0
            while True:
                if i >= len(turn.events):
                    if not await turn.wait(i, 10.0):
                        writer.write(b": hb\n\n")
                        await writer.drain()
                    continue
                kind, data = turn.events[i]
                i += 1
                if kind == "text":
                    writer.write(netio.sse_data(dict(base, choices=[{"index": 0, "delta": {"content": data}, "finish_reason": None}])))
                elif kind == "phase":
                    writer.write(netio.sse("nox_phase", data))
                elif kind == "meta":
                    writer.write(netio.sse("nox_meta", data))
                elif kind == "done":
                    writer.write(netio.sse_data(dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}])))
                    writer.write(netio.sse("nox_meta", {"turn_id": turn.id, "path": turn.trace.get("path"), "trace": "/v1/core/trace/" + turn.id, "status": data["status"]}))
                    writer.write(b"data: [DONE]\n\n")
                    await writer.drain()
                    return
                await writer.drain()
        except (ConnectionError, OSError):
            return        # клиент ушёл: ход продолжается и сохранится; остановить можно только STOP

    async def start(self):
        self.server = await asyncio.start_server(self.handle, self.cfg.host, self.cfg.port)
        try:
            import nox_intent
            self.intent = nox_intent.attach()
            if self.intent:
                self._intent_task = asyncio.create_task(self.intent.loop())
        except Exception:
            self.intent = None
        return self.server


async def amain():
    core = Core()
    srv = await core.start()
    print("NOX CORE %s на %s:%s  органы: %s  совесть: %s" % (VERSION, core.cfg.host, core.cfg.port, ",".join(core.organs.status()) or "нет", core.cfg.conscience), flush=True)
    async with srv:
        await srv.serve_forever()


if __name__ == "__main__":
    asyncio.run(amain())
