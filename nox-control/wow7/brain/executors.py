"""8 исполнителей NOX CORE. Единый интерфейс: await Executor(core)(st) -> результат; у каждого name, budget_s, run(st), degraded(st).
Обёртка меряет мс, ловит таймаут/исключение (орган не роняет ход), пишет запись в трассу хода."""
import asyncio
import json
import os
import re
import time

import conscience as C
import organs as O
import netio

try:
    import optlayer as OPTL            # c400: телеметрия, семантический кэш, GLM-судья (необязательно)
except Exception:
    OPTL = None

try:
    from bridge_intro import intro_safe, canned as _canned, kind_of, SYSTEM as INTRO_SYSTEM
except Exception:        # RTE недоступен - минимальные заготовки
    INTRO_SYSTEM, kind_of = None, None
    intro_safe = None

    def _canned(text):
        return "Принял, мессир, секунду."

INTRO_BANK = ("Мессир, мне нужно чуть больше времени.", "Мессир, ответ задерживается — проверяю его.",
              "Мессир, я ещё собираю факты.", "Мессир, потребуется немного времени.")
INTRO_NOTE = "\n\n[Мессиру уже показана короткая фраза-отклик. Не начинай с подтверждения и приветствия, сразу к содержанию ответа.]"

GREET = re.compile(r"^\W*(привет\w*|здравствуй\w*|добр\w+ (?:день|вечер|утро|ночи)|хай|салют|приветствую)\W*$", re.I)
SMALL = re.compile(r"^\W*(спасибо|благодарю|ок|окей|ага|угу|да|нет|понял\w*|ясно|пока|до связи|ты тут|ты здесь|как дела|как жизнь|как оно|что нового)\W*$", re.I)
STOP = re.compile(r"^\W*(stop|стоп|стой|хватит|остановись|отмена|замолчи)\W*$", re.I)
YES = re.compile(r"^\W*(да|подтверждаю|давай|удаляй|удали|ок|окей|yes|согласен)\W*$", re.I)
NO = re.compile(r"^\W*(нет|не надо|отмена|отменяю|no|не удаляй)\W*$", re.I)
UNDO = re.compile(r"верни\w*\s+удал|отмени\w*\s+удален|восстанови\w*\s+удал", re.I)
DELETE = re.compile(r"\bудал\w*", re.I)
HISTORY_OBJ = re.compile(r"запрос|сообщен|реплик", re.I)
DEEP_KW = re.compile(r"почему|докажи|сравни|проанализ\w*|оцени|спланируй|архитектур\w*|стратеги\w*|объясни|разбер\w+|рассчитай|посчитай|вывед\w+|код\b|скрипт|баг|ошибк|план\b", re.I)
THINK_KW = re.compile(r"подума\w*|глубоко|тщательно|детально|подробн\w*|в\s+деталях|think", re.I)
FAST_KW = re.compile(r"\b(быстро|коротко|в двух словах)\b", re.I)
TASK_RE = re.compile(r"^\W*(?:нокс[,\s]+)?(сделай|напиши|создай|запусти|найди|открой|проверь|исправь|собери|посчитай|переведи|составь|добавь)", re.I)
NUMW = {"один": 1, "одну": 1, "одн": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10}
ANGER = re.compile(r"блять|чёрт|черт|херн|позор|не работает|бесит|достал", re.I)
JOY = re.compile(r"спасибо|круто|отлично|молодец|супер|класс", re.I)


class Exec:
    name = "?"
    budget_s = 1.0

    def __init__(self, core):
        self.core = core

    async def __call__(self, st):
        rec = {"name": self.name, "budget_ms": int(self.budget_s * 1000) if self.budget_s else None}
        st.turn.trace["executors"].append(rec)
        t0 = time.monotonic()
        try:
            r = await (asyncio.wait_for(self.run(st), self.budget_s) if self.budget_s else self.run(st))
            rec["ok"] = True
            rec.setdefault("status", "ok")
            return r
        except asyncio.TimeoutError:
            rec.update(ok=False, error="budget_exceeded", status="timeout")
            return self.degraded(st)
        except asyncio.CancelledError:
            rec.update(ok=False, error="cancelled", status="cancelled")
            raise
        except Exception as e:
            rec.update(ok=False, status="error", error="%s: %s" % (type(e).__name__, e))
            return self.degraded(st)
        finally:
            rec["ms"] = int((time.monotonic() - t0) * 1000)

    def degraded(self, st):
        return None

    def note(self, st, text):
        for r in reversed(st.turn.trace["executors"]):
            if r["name"] == self.name:
                r["note"] = text
                if text == "skipped":
                    r["status"] = "skipped"
                return


class State:
    def __init__(self, core, turn, conv, user_text, history, opts):
        self.core, self.turn, self.conv, self.user_text, self.history, self.opts = core, turn, conv, user_text, history, opts
        self.intent, self.lang, self.emotion, self.speaker, self.hint = "question", "ru", "neutral", "owner", None
        self.focus_block, self.mem, self.mood = "", {}, {}
        self.path, self.glm_state, self.degraded = "reflex", "unknown", []
        self.block_policy = "full"
        self.want_intro, self.intro_task, self.intro_text = False, None, ""
        self.draft, self.streamed, self.guard, self.final = "", False, None, ""
        self.findings, self.actions = [], []
        self.action = None
        self.arm, self.model, self.pred = None, None, None
        self.messages_extra = None
        self.council = False
        self.advice, self.advisors = "", []        # ADV-06: compose_prompt советников и их тексты (для детектора advisor_copy)
        self.reply_settings = {"max_tokens": 1500, "mode": "auto"}
        self.first_visible_token = asyncio.Event()

    @property
    def prev(self):
        return [m["content"] for m in self.history if m.get("role") == "assistant" and not m.get("control")][-5:]

    def block_full(self):
        mem = []
        if self.mem.get("core"):
            mem.append(str(self.mem["core"]).strip())
        mem += ["- " + str(r)[:300] for r in (self.mem.get("recalled") or [])[:5]]
        parts = [p for p in (self.focus_block, "\n".join(mem)) if p]
        mood = self.mood.get("mood_label")
        if mood:
            parts.insert(0, "Настроение: %s." % mood)
        return "\n\n".join(parts)

    def block_for_model(self):
        if self.block_policy == "none":
            return ""
        if self.block_policy == "mood":
            m = self.mood.get("mood_label")
            return ("Настроение: %s." % m) if m else ""
        return self.block_full()

    def user_content(self):
        b = self.block_for_model()
        t = self.advice or self.user_text       # СОВЕТ: рамка <данные> с мнениями советников + исходный вопрос (compose_prompt)
        if b:
            t = "<внутреннее_состояние>\n%s\n%s\n</внутреннее_состояние>\n\n%s" % (b, O.BLOCK_RULE, self.advice or self.user_text)
        if self.intro_text:
            t += INTRO_NOTE
        return t

    def cctx(self):
        return {"block": self.block_full(), "user_text": self.user_text, "intent": self.intent, "prev": self.prev,
                "asked_status": self.intent == "telemetry_q", "advisors": list(self.advisors), "speaker": self.speaker}


# ---------------------------------------------------------------- 1. Восприятие
class Perception(Exec):
    name, budget_s = "perception", 0.15

    async def run(self, st):
        t = st.user_text.strip()
        conv = st.conv
        try:
            from actions import AnswerSettings
            settings_request = AnswerSettings.is_request(t)
        except Exception:
            settings_request = False
        st.lang = "ru" if re.search(r"[а-яё]", t, re.I) else ("en" if re.search(r"[a-z]", t, re.I) else "ru")
        st.speaker = st.opts.get("speaker") or self.core.cfg.default_speaker
        try:
            from actions import AnswerSettings
            st.reply_settings, _ = AnswerSettings(self.core).get(st.speaker)
        except Exception:
            st.reply_settings = {"max_tokens": 1500, "mode": "auto"}
        st.opts = dict(st.opts or {})
        if st.opts.get("mode") in (None, "", "auto"):
            st.opts["mode"] = st.reply_settings.get("mode", "auto")
        if st.opts.get("max_tokens") is None:
            st.opts["max_tokens"] = st.reply_settings.get("max_tokens", 1500)
        st.emotion = "irritated" if ANGER.search(t) else ("warm" if JOY.search(t) else "neutral")
        st.hint = {"fast": "reflex", "deep": "thought", "max": "deep"}.get(st.opts.get("mode"))
        if FAST_KW.search(t):
            st.hint = st.hint or "reflex"
        if THINK_KW.search(t):
            st.hint = "deep" if st.hint != "deep" else st.hint
        pend = conv.pending if conv.pending and conv.pending["until"] > time.time() else None
        if conv.pending and not pend:
            conv.pending = None
        if STOP.match(t):
            st.intent = "stop"
        elif pend and YES.match(t):
            st.intent = "confirm"
        elif pend and NO.match(t):
            st.intent = "deny"
        elif UNDO.search(t):
            st.intent = "undo"
        elif DELETE.search(t) and HISTORY_OBJ.search(t):
            st.intent = "delete_history"
        elif GREET.match(t):
            st.intent = "greeting"
        elif SMALL.match(t):
            st.intent = "smalltalk"
        elif C.is_status_question(t) and len(t.split()) <= 12:
            st.intent = "telemetry_q"
        elif settings_request:
            st.intent = "answer_settings"
        elif TASK_RE.match(t):
            st.intent = "task"
        else:
            st.intent = "question"
        if pend and st.intent not in ("confirm", "deny"):
            conv.pending = None
            st.turn.trace["pending_cancelled"] = True      # другая реплика отменяет ожидающее действие

    def degraded(self, st):
        st.intent = "question"


CORRECT = re.compile(r"\b(нет,? не так|неправильно|не то|ты ошибся|ошибаешься|не верно|неверно|переделай|я не это просил)", re.I)


class Predictive(Exec):
    """Стык predictive_self: сначала закрываем прогноз прошлого хода реакцией на ЭТУ реплику, потом фиксируем прогноз на этот ход."""
    name, budget_s = "predictive", 0.25

    async def run(self, st):
        core, t = self.core, st.user_text
        if st.opts.get("eval"):                       # ход бенчмарка: ни прогноза, ни закрытия прошлого прогноза (MIND R2)
            self.note(st, "skipped")
            return
        prev = next((m["turn_id"] for m in reversed(st.history) if m["role"] == "assistant" and not m.get("control") and m.get("turn_id")), None)
        if prev and st.intent not in ("stop",):
            corrected = bool(CORRECT.search(t))
            label = "correct" if corrected else "frustrated" if ANGER.search(t) else "approve" if JOY.search(t) else "neutral"
            n = len(t.split())
            react = {"label": label, "valence": {"correct": -0.5, "frustrated": -0.8, "approve": 0.8}.get(label, 0.0),
                     "length": "short" if n < 6 else "medium" if n < 30 else "long", "followup": True}
            st.turn.trace["late"] = {"prev_turn": prev, "label": label, **core.organs.observe_late(prev, react, corrected)}
        if st.intent in ("stop", "confirm", "deny", "undo", "delete_history"):
            return
        ctx = {"greeting": "chat", "smalltalk": "chat", "telemetry_q": "chat", "question": "question", "task": "task"}.get(st.intent, "question")
        st.pred = core.organs.predict(st.turn.id, ctx, t)
        if st.pred:
            st.turn.trace["predicted"] = {"success_p": st.pred["pred"]["outcome"]["success_p"], "label": st.pred["pred"]["creator"]["label"]}

    def degraded(self, st):
        st.turn.trace["errors"].append("predictive: недоступен")


# ---------------------------------------------------------------- 2. Внимание
class Attention(Exec):
    name, budget_s = "attention", 0.02

    async def run(self, st):
        st.focus_block = self.core.organs.attention(st.user_text, st.turn.id)
        st.mood = self.core.organs.mood()


def _mentions(x, ids):
    if isinstance(x, dict):
        if str(x.get("turn_id") or x.get("episode") or x.get("id") or "") in ids:
            return True
        x = json.dumps(x, ensure_ascii=False)
    s = str(x)
    return any(i in s for i in ids)


def ablate_memory(mem, ids):
    """Убрать из выдачи памяти записи, относящиеся к эпизодам ids (turn_id/id записи или упоминание id в тексте). -> (mem, сколько убрано)."""
    ids = set(ids)
    mem = dict(mem or {})
    rec = list(mem.get("recalled") or [])
    keep = [r for r in rec if not _mentions(r, ids)]
    n = len(rec) - len(keep)
    mem["recalled"] = keep
    core = mem.get("core")
    if isinstance(core, str) and any(i in core for i in ids):
        lines = core.split("\n")
        left = [l for l in lines if not any(i in l for i in ids)]
        n += len(lines) - len(left)
        mem["core"] = "\n".join(left)
    return mem, n


# ---------------------------------------------------------------- 3. Память
class Memory(Exec):
    name, budget_s = "memory", 0.3

    async def run(self, st):
        if st.intent in ("greeting", "smalltalk", "stop", "confirm", "deny", "undo", "delete_history") or not self.core.organs.has("memory"):
            self.note(st, "skipped")
            return
        loop = asyncio.get_running_loop()
        st.mem = await loop.run_in_executor(None, self.core.organs.memory, st.user_text, st.turn.id) or {}
        ab = st.opts.get("ablate")
        if ab:                                         # X-NOX-Ablate: эпизод выключается из ретривала только на этот ход
            st.mem, n = ablate_memory(st.mem, ab)
            st.turn.trace.setdefault("ablate", {})["dropped_recalled"] = n


# ---------------------------------------------------------------- 4. Решатель
class Decider(Exec):
    name, budget_s = "decider", 0.5

    async def run(self, st):
        st.glm_state = await self.core.glm_state()
        it, hint = st.intent, st.hint
        if it == "telemetry_q" and OPTL is not None:      # c400: вопрос «как сервер?» - отвечать по РЕАЛЬНЫМ замерам (nvidia-smi, /proc)
            try:
                tb = OPTL.get().telemetry_block(st.user_text)
                if tb:
                    st.advice = tb
                    st.turn.trace["telemetry"] = "real"
            except Exception:
                pass
        if it in ("delete_history", "undo", "confirm", "deny", "answer_settings"):
            st.path = "action"
            return
        if it in ("greeting", "smalltalk"):
            st.path, st.block_policy = "reflex", "mood" if st.mood.get("mood_label") else "none"
            if it == "greeting":
                st.block_policy = "none"
            return
        if it == "task":
            for p in self.core.planners:
                plan = p.match(st.user_text)
                if plan:
                    st.action, st.path = (p, plan), "action"
                    return
        if not hint and it in ("question", "task", "telemetry_q"):
            arm = self.solver(st)
            if arm:
                st.arm = arm
                want = {"reflex": "reflex", "thought": "thought", "deep": "deep", "council": "deep"}[arm]
                if arm == "council":
                    st.council = True            # ADV-04/06: Reason позовёт Council до генерации
                st.path = want
                st.block_policy = "full"
                if want in ("thought", "deep"):
                    st.want_intro = True
                    if st.glm_state in ("busy", "down"):
                        st.degraded.append("glm_" + st.glm_state)
                        st.path = "reflex"
                return
        words = len(st.user_text.split())
        deep_kw = bool(DEEP_KW.search(st.user_text))
        if hint:
            want = hint
        elif it == "telemetry_q":
            want = "reflex"
        elif deep_kw and words > 6 or words > 40:
            want = "deep" if (THINK_KW.search(st.user_text) or words > 80) else "thought"
        elif words <= 6 and not deep_kw and it != "task":
            want = "reflex"
        else:
            want = "thought"
        st.path = want
        st.block_policy = "full"
        if want in ("thought", "deep"):
            st.want_intro = True
            if st.glm_state in ("busy", "down"):
                st.degraded.append("glm_" + st.glm_state)
                st.path = "reflex"       # отвечает быстрая; вступление остаётся (want_intro)

    def solver(self, st):
        """Обучаемая политика (MIND/M1_ARCH). Любой сбой -> None, дальше работают правила."""
        try:
            ctx = {"deep_up": st.glm_state != "down", "fast_up": True, "mode": st.opts.get("mode"), "history_turns": len(st.history) // 2,
                   "intent": {"question": "question", "task": "task", "telemetry_q": "chat"}[st.intent], "creator": st.speaker == "owner",
                   "quiet": False}
            res = self.core.organs.solver_run(st.user_text, ctx, st.turn.id)
            if not res:
                return None
            self.note(st, "solver arm=%s rev=%s" % (res.get("arm"), res.get("policy_rev")))
            return res.get("arm")
        except Exception as ex:
            st.turn.trace["errors"].append("solver: %s" % ex)
            return None

    def degraded(self, st):
        st.path = "reflex"
        st.glm_state = "unknown"


# ---------------------------------------------------------------- 5. Интуиция (вступление)
class Intuition(Exec):
    name, budget_s = "intuition", 2.0

    def pick(self, st):
        used = {" ".join(C.stems(p)) for p in st.prev}
        for b in INTRO_BANK:
            if " ".join(C.stems(b)) not in used:
                return b
        return INTRO_BANK[len(st.prev) % len(INTRO_BANK)]

    async def run(self, st):
        # Intro is off by default. When enabled, it is temporary and shown only if no answer token arrives in 4 s.
        if os.environ.get("RTE_INTRO", "0").strip().lower() not in ("1", "true", "yes", "on"):
            self.note(st, "disabled")
            return
        try:
            await asyncio.wait_for(st.first_visible_token.wait(), timeout=4.0)
            self.note(st, "skipped:first_token<=4s")
            return
        except asyncio.TimeoutError:
            if st.draft.strip() or st.turn.parts or st.turn.stop_requested:
                self.note(st, "skipped:answer_started")
                return
        text, src = None, "canned"
        if INTRO_SYSTEM and intro_safe:
            k = kind_of(st.user_text)
            msgs = [{"role": "system", "content": INTRO_SYSTEM % (k, st.mood.get("mood_label") or "ровное")},
                    {"role": "user", "content": "Тип запроса: %s. (Содержание запроса тебе не показано намеренно.)" % k}]
            try:
                raw = await self.core.fast.chat(msgs, max_tokens=40, temperature=0.7, timeout=1.7, prio=0)
                raw = (raw or "").strip().split("\n")[0].strip('"«» ')
                ok, why = intro_safe(raw, st.user_text)
                if ok and not C.Conscience().review(raw, {"prev": st.prev, "intent": "greeting"}):
                    text, src = raw, "fast"
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
        st.intro_text = text or self.pick(st)
        self.note(st, src)
        st.turn.trace["intro_text"] = st.intro_text
        await st.turn.emit_text(st.intro_text + "\n\n")
        st.turn.emit_meta("phase", {"phase": "intro", "source": src})

    def degraded(self, st):
        if not st.intro_text:
            st.intro_text = self.pick(st)
        return None


# ---------------------------------------------------------------- 5b. Совет (ADV-04/06)
class Council(Exec):
    """Путь СОВЕТ: спросить внешних советников через хаб (ADV/advisor_hub, `/v1/advisors/ask`), результат - материал в рамке <данные>.
    Зовёт: (а) arm=council от Решателя; (б) авто: уверенность прогноза < порога (AutoGate хаба сам решает по лимитам в час/сутки и privacy=private).
    Не зовёт: РЕФЛЕКС/ДЕЙСТВИЕ, телеметрия, eval-ходы, личная память (хаб тоже отказывает). Нет NOX_ADV_URL или хаб лежит -> ход идёт без советников (degraded)."""
    name, budget_s = "council", 28.0
    PERSONAL = re.compile(r"помнишь|напомни|мой пароль|моя семья|паспорт|из памяти|мо[йяеи]\s+(?:жена|муж|дет|сын|дочь|мам|пап)", re.I)

    def url(self):
        return (getattr(self.core.cfg, "adv_url", None) or __import__("os").environ.get("NOX_ADV_URL") or "").rstrip("/")

    def confidence(self, st):
        try:
            return float(st.pred["pred"]["outcome"]["success_p"]) if st.pred else None
        except (KeyError, TypeError, ValueError):
            return None

    async def run(self, st):
        explicit = bool(getattr(st, "council", False))
        base = self.url()
        conf = self.confidence(st)
        if st.opts.get("eval") or st.path == "action" or st.intent not in ("question", "task"):
            return self.note(st, "skipped")
        if not base:
            if explicit:
                st.degraded.append("council_no_hub")
            return self.note(st, "skipped")
        if not explicit and (conf is None or conf >= 0.55 or (st.path == "reflex" and not st.degraded) or len(st.user_text.split()) < 4):
            return self.note(st, "skipped")
        body = {"question": st.user_text[:1500], "path": st.path, "privacy": "private", "source": "core" if explicit else "auto", "deadline_s": 20,
                "contains_memory": bool(self.PERSONAL.search(st.user_text))}
        if explicit:
            body["n"] = 2
        else:
            body["confidence"] = conf
        tok = __import__("os").environ.get("NOX_ADV_TOKEN")
        status, obj = await netio.json_call("POST", base + "/v1/advisors/ask", body, 24.0, {"Authorization": "Bearer " + tok} if tok else None)
        if status != 200 or not isinstance(obj, dict):
            st.degraded.append("council_http_%s" % status)
            return self.note(st, "http_%s" % status)
        if not obj.get("ok"):
            return self.note(st, "skipped:%s" % (obj.get("skipped") or obj.get("error") or obj.get("reason") or "no"))
        answers = [a for a in obj.get("answers", []) if a.get("text")]
        if not answers or not obj.get("compose_prompt"):
            return self.note(st, "no_answers")
        st.advice = obj["compose_prompt"]
        st.advisors = [a["text"] for a in answers]
        st.turn.trace["council"] = {"source": body["source"], "advisors": [a.get("advisor") for a in answers], "n": len(answers), "confidence": conf,
                                    "agreement": (obj.get("agreement") or {}).get("label")}
        st.turn.emit_meta("phase", {"phase": "council", "advisors": [a.get("advisor") for a in answers]})
        self.note(st, "advisors=%d" % len(answers))

    def degraded(self, st):
        st.degraded.append("council_failed")


# ---------------------------------------------------------------- 6. Разум
class Reason(Exec):
    name, budget_s = "reason", None

    def history_msgs(self, st, n=8):
        return [{"role": m["role"], "content": m["content"]} for m in st.history if m.get("role") in ("user", "assistant") and not m.get("control")][-n:]

    def msgs(self, st, glm):
        system = self.core.organs.soul() if glm else O.FAST_SOUL
        if not glm and st.intent in ("greeting", "smalltalk"):
            system += " Сейчас светская реплика: ответь 1-3 живыми фразами."
        return [{"role": "system", "content": system}] + self.history_msgs(st) + [{"role": "user", "content": st.user_content()}]

    async def run(self, st):
        st.cache_hit = None
        if OPTL is not None:                                # c400: семантический кэш (explore-попадание: свежий ответ + суд)
            try:
                h = OPTL.get().lookup(st, self.core.organs.soul())
            except Exception:
                h = None
            if h is not None and not h.explore:
                st.draft, st.model = h.answer, "cache"
                st.turn.trace["cache"] = {"hit": True, "sim": round(h.sim, 3), "exact": h.exact}
                st.turn.trace["reason_attempts"] = ["cache"]
                return
            st.cache_hit = h
        if st.path in ("thought", "deep", "reflex") and st.intent in ("question", "task"):
            await Council(self.core)(st)               # ADV-06: СОВЕТ (явный arm=council или низкая уверенность); сбой не роняет ход
        if st.path in ("thought", "deep") and st.glm_state in ("up", "unknown"):
            if await self._glm(st):
                return
        await self._fast(st)

    async def _glm(self, st):
        core, cfg = self.core, self.core.cfg
        try:
            requested_tokens = int(st.opts.get("max_tokens", 1500))
        except (TypeError, ValueError):
            requested_tokens = 1500
        # Thinking may remain enabled in some server builds; keep enough output budget for that fallback.
        glm_tokens = max(1500, min(3000, requested_tokens))
        payload = {"model": "glm", "messages": self.msgs(st, True), "stream": True,
                   "max_tokens": glm_tokens, "chat_template_kwargs": {"enable_thinking": False}}
        st.guard = C.StreamGuard(core.conscience, st.cctx())
        writer, first, got = None, True, False
        core.glm_inflight += 1
        try:
            try:
                status, hdrs, reader, writer = await netio.open_request("POST", cfg.glm_url.rstrip("/") + "/v1/chat/completions", payload, timeout=5.0)
            except (OSError, asyncio.TimeoutError) as e:
                st.degraded.append("glm_down")
                return False
            st.turn.writers.append(writer)
            if status != 200:
                st.degraded.append("glm_http_%d" % status)
                return False
            st.turn.emit_meta("phase", {"phase": "thinking", "path": st.path})
            it = netio.iter_sse_data(reader, hdrs).__aiter__()
            deadline = time.monotonic() + cfg.glm_total_s
            while True:
                left = min(cfg.glm_first_token_s if first else cfg.glm_idle_s, deadline - time.monotonic())
                if left <= 0:
                    raise asyncio.TimeoutError()
                try:
                    data = await asyncio.wait_for(it.__anext__(), left)
                except StopAsyncIteration:
                    break
                if data == "[DONE]":
                    break
                try:
                    d = ((json.loads(data).get("choices") or [{}])[0].get("delta") or {})
                except ValueError:
                    continue
                piece = d.get("content") or ""          # reasoning_content намеренно игнорируется: думание не текст
                if not piece:
                    continue
                st.first_visible_token.set()
                first = False
                got = True
                if st.intro_task is not None and not st.intro_task.done():
                    await asyncio.wait({st.intro_task}, timeout=3.0)
                for s in st.guard.feed(piece):
                    st.draft += s
                    await st.turn.emit_text(s)
            for s in st.guard.flush():
                st.draft += s
                await st.turn.emit_text(s)
        except asyncio.TimeoutError:
            st.degraded.append("glm_first_token_timeout" if first else "glm_stalled")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            st.degraded.append("glm_error:" + type(e).__name__)
        finally:
            core.glm_inflight -= 1
            if writer is not None:
                writer.close()
                st.turn.upstream_closed = True
        st.streamed = bool(st.draft.strip())
        if st.streamed:
            st.model = "glm"
        if st.guard.dropped:
            st.turn.trace["conscience"]["stream_dropped"] = st.guard.dropped
        return st.streamed

    async def _fast(self, st):
        if st.intro_task is not None and not st.intro_task.done():
            await asyncio.wait({st.intro_task}, timeout=3.0)     # вступление всегда раньше ответа
        try:
            mt = max(300, min(3000, int(st.opts.get("max_tokens", 1500))))
        except (TypeError, ValueError):
            mt = 1500
        tries = [(0.8, mt), (1.0, mt)]
        log = []
        for temp, m in tries:
            try:
                txt = await self.core.fast.chat(self.msgs(st, False), max_tokens=m, temperature=temp, timeout=self.core.cfg.fast_timeout_s, prio=0)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.append("err:%s" % type(e).__name__)
                continue
            txt = (txt or "").strip()
            if txt:
                st.draft, st.model = txt, "fast"
                st.turn.trace["reason_attempts"] = log + ["ok@T%.1f" % temp]
                return
            log.append("empty@T%.1f" % temp)
        # другой исполнитель: GLM, если свободен
        if st.glm_state == "up" and not st.turn.glm_tried and not self.core.glm_inflight:
            st.turn.glm_tried = True
            try:
                txt = await self.core.glm_once(self.msgs(st, True), max(1500, mt), 12.0)
                if txt.strip():
                    st.draft, st.model = txt.strip(), "glm"
                    st.turn.trace["reason_attempts"] = log + ["ok@glm"]
                    return
                log.append("empty@glm")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.append("glm_err:%s" % type(e).__name__)
        st.turn.trace["reason_attempts"] = log + ["exhausted"]
        st.draft = ""


# ---------------------------------------------------------------- 7. Совесть
class ConscienceExec(Exec):
    name, budget_s = "conscience", 12.0

    async def rewrite(self, st, text, findings):
        prev = [p[:80] for p in st.prev[-3:]]
        sysm = ("Перепиши ответ NOX Создателю. Обращайся на «вы», при прямом обращении используй «мессир»; отвечай по существу и с проверяемыми фактами. "
                "Не используй пафос, лесть, самоуничижение, заготовленные приветствия и шаблоны; не соглашайся без основания; чувства называй только при подтверждённой причине. "
                "Короткий ответ давай на короткую реплику, для развёрнутого вопроса дай достаточное объяснение. Не повторяй обороты прошлых ответов: %s. "
                "Нарушения: %s. Выведи только текст ответа." % ("; ".join(prev) or "-", ", ".join(sorted({f.code for f in findings}))))
        use_glm = st.path == "deep" and st.glm_state == "up" and self.core.cfg.rewrite_glm
        leaky = any(f.code in ("inner_echo", "unsolicited_telemetry", "template") for f in findings)
        draft = "(не показан: пересказывал внутреннее состояние; ответь по сути реплики заново)" if leaky else text[:900]
        msgs = [{"role": "system", "content": sysm}, {"role": "user", "content": "Реплика мессира: %s\nЧерновик: %s" % (st.user_text, draft)}]
        if use_glm:
            return await self.core.glm_once(msgs, 600, 20.0)
        return await self.core.fast.chat(msgs, max_tokens=220, temperature=0.9, timeout=self.core.cfg.rewrite_budget_s, prio=0)

    async def finalize(self, st, text):
        cons, ctx = self.core.conscience, st.cctx()
        rec = st.turn.trace["conscience"]
        fs = cons.review(text, ctx) if text.strip() else [C.Finding("empty", "пустой ответ")]
        regenerate_empty = False
        rec["findings"] = [f.to_dict() for f in fs]
        if not fs:
            return cons.clamp(text, ctx)
        if cons.mode == "shadow":
            rec["actions"].append("shadow_no_change")
            return text
        if text.strip():
            text, done = cons.repair(text, fs, ctx)
            rec["actions"] += done
            regenerate_empty = not text.strip() and any(a in done for a in ("strip_banned_opener", "strip_flattery_pathos", "strip_unreasoned_agreement"))
            fs = cons.review(text, ctx) if text.strip() else [C.Finding("empty", "после ремонта пусто")]
        if fs:
            new = ""
            if any(f.code != "empty" for f in fs) or regenerate_empty:
                try:
                    new = await self.rewrite(st, text, fs)
                    new, _ = C.strip_service(re.sub(r"<think>.*?</think>", "", new or "", flags=re.S).strip())
                    rec["actions"].append("rewrite")
                    rec["rewrites"] = rec.get("rewrites", 0) + 1
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    rec["actions"].append("rewrite_failed:%s" % type(e).__name__)
            fs2 = cons.review(new, ctx) if new.strip() else [C.Finding("empty")]
            rec["after_rewrite"] = [f.code for f in fs2]
            if fs2:
                rec["actions"].append("safe_answer")
                return C.safe_answer(st.intent, st.prev)
            text = new
        return cons.clamp(text, ctx)

    async def run(self, st):
        st.turn.emit_meta("phase", {"phase": "conscience"})
        draft = st.draft.strip()
        if st.streamed:
            fs = self.core.conscience.review(draft, st.cctx()) if draft.strip() else [C.Finding("empty", "пустой поток")]
            fs = [f for f in fs if f.code in ("empty", "repeat_turns", "feeling_no_cause", "inner_echo", "unsolicited_telemetry", "template", "as_ai", "service_lines", "flattery_open", "banned_opener", "flattery_pathos", "address_vy", "agree_without_reason", "advisor_copy")
                  or f.code.startswith("v0_")]
            if not fs or self.core.conscience.mode == "shadow":
                st.turn.trace["conscience"]["findings"] = [f.to_dict() for f in fs]
                st.final = draft
                return
            new = await self.finalize(st, draft)
            st.final = new
            if new != draft:
                full = (st.intro_text + "\n\n" if st.intro_text else "") + new
                st.turn.replace_text(full)
                st.turn.emit_meta("meta", {"replace": full})
            return
        new = await self.finalize(st, draft)
        st.final = new
        for s in re.split(r"(?<=[.!?…])\s+", new):
            if s:
                await st.turn.emit_text(s + " ")

    def degraded(self, st):
        # бюджет Совести исчерпан до вердикта: безопасный ответ лучше непроверенного
        st.turn.trace["conscience"]["actions"].append("budget_safe_answer")
        if not st.streamed:
            st.final = C.safe_answer(st.intent, st.prev)
            st.turn.parts.append(st.final)


# ---------------------------------------------------------------- 8. Летописец
class Chronicler(Exec):
    name, budget_s = "chronicler", None

    async def run(self, st):
        core, turn = self.core, st.turn
        reply = turn.text().strip()
        g = getattr(core, "genome", None)
        if g is not None:
            try:
                g.after_turn(turn.id, reply, [])
            except Exception:
                pass
        if OPTL is not None and not st.opts.get("eval"):
            core.bg.once("optpost:" + turn.id, lambda: self._cache_post(st))
        started = core.bg.once("chron:" + turn.id, lambda: self._job(st, reply))
        self.note(st, "scheduled" if started else "duplicate_skipped")

    async def _cache_post(self, st):
        """c400: положить проверенный ответ в кэш; на explore-попадании судья (GLM :8081, клиент) сравнивает кэш и свежий -> обратная связь порогу."""
        try:
            o = OPTL.get()
            final = (st.final or "").strip()
            if st.model not in ("fast", "glm") or not final or st.turn.trace.get("conscience", {}).get("verdict") != "pass":
                return
            soul = self.core.organs.soul()
            hit = getattr(st, "cache_hit", None)
            if hit is not None:
                loop = asyncio.get_running_loop()
                p = await asyncio.wait_for(loop.run_in_executor(None, o.judge_sync, st.user_text, hit.answer, final), 150.0)
                if p is not None:
                    o.feedback(hit, p >= 0.4)
                    st.turn.trace["cache"] = {"explore": True, "judge_p_cached_better": round(p, 3)}
                else:
                    ok = o.cache.agreed(hit.answer, final)
                    o.feedback(hit, ok)
                    st.turn.trace["cache"] = {"explore": True, "judge": "unavailable", "agreed": ok}
            o.store(st, final, soul)
        except Exception:
            pass

    async def _job(self, st, reply):
        t0 = time.monotonic()
        rec = {"status": "running"}
        st.turn.trace["chronicler"] = rec
        try:
            loop = asyncio.get_running_loop()
            ev = bool(st.opts.get("eval"))
            u, r_ = (("[EVAL] " + st.user_text), ("[EVAL] " + reply)) if ev else (st.user_text, reply)      # метка для очистки по X-NOX-Eval
            await asyncio.wait_for(loop.run_in_executor(None, self.core.organs.after, u, r_, st.turn.id), 10.0)
            tr = st.turn.trace
            if ev:
                rec["mind"] = {"skipped": "eval"}              # бенчмарк не обучает ни Решатель, ни Предсказатель, ни сон
                rec["status"] = "done"
                rec["ms"] = int((time.monotonic() - t0) * 1000)
                self.core.persist_trace(st.turn)
                return
            ok = tr["conscience"].get("verdict") == "pass"
            empty = "exhausted" in (tr.get("reason_attempts") or [])
            info = {"outcome": {"conscience_ok": ok, "rewrites": tr["conscience"].get("rewrites", 0), "empty": empty, "stopped": False,
                                "latency_s": tr.get("total_ms", 0) / 1000.0},
                    "success": ok and not empty, "latency_s": max(tr.get("total_ms", 0) / 1000.0, 0.05),
                    "ctx": {"greeting": "chat", "smalltalk": "chat", "telemetry_q": "chat", "question": "question", "task": "task"}.get(st.intent, "question"),
                    "path": tr.get("path_code")}
            rec["mind"] = await asyncio.wait_for(loop.run_in_executor(None, self.core.organs.observe_turn, st.turn.id, info), 5.0)
            rec["status"] = "done"
        except Exception as e:
            rec["status"] = "failed"
            rec["error"] = "%s: %s" % (type(e).__name__, e)
        rec["ms"] = int((time.monotonic() - t0) * 1000)
        self.core.persist_trace(st.turn)
