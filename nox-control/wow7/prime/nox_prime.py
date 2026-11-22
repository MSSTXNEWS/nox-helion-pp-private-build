"""nox_prime: единый режим чата NOX «Prime» — один умный, всё помнящий, растущий NOX.

Шлюз зовёт ровно две функции:
  prime.build(user_text, history, turn_id) -> {"messages", "route", "params", "static_hash", "info"}
  prime.after_reply(user_text, reply_text, turn_id)
Внутри собираются все органы v7 (каждый необязателен; упавший орган не роняет чат — пишется в info["errors"]):
  signature()            -> (текст, хеш)   характер (PER/personality.Personality.signature) — в СТАТИЧНОЙ части
  affect                 -> .snapshot(), .on_owner_message(text)   (EMO/affect_loop.Affect)
  workspace              -> .post(key,text,salience,kind), .render_block(extra_lines)   (CON/nox_workspace.Workspace)
  self_model             -> .render() -> str, .note_owner_message()   (CON/nox_self_model_live.LiveSelfModel)
  beliefs                -> .prompt_lines(query, k)   (PER/beliefs.Beliefs)
  narrative()            -> str   (PER/development.Development.narrative)
  memory(text, turn_id)  -> {"core": str, "recalled": [str]}   (qs6 recall_api/memory_layer)
  atlas()                -> str   короткая сводка устройства (WORLD/self_atlas)
  router(text, ctx)      -> {"tier": "fast"|"deep"|"deep_think", ...}   (RTE/router), иначе встроенная эвристика
Порядок сообщений бережёт KV-кэш llama.cpp: [system = душа + характер] + история + [user = <внутреннее_состояние> + вопрос].
Динамика в историю НЕ попадает (шлюз сохраняет в историю исходный user_text).
"""
import hashlib
import re
import time

DEEP_THINK = re.compile(r"\b(почему|докажи|обоснуй|план|стратеги|архитектур|сравни|проанализируй|анализ|рассчитай|посчитай|"
                        r"оптимизир|напиши (код|скрипт|программу)|отлад|ошибк|баг|теорем|физик|исследу)", re.I)
SMALL_TALK = re.compile(r"^\s*(привет|здравствуй|доброе утро|добрый (день|вечер)|спокойной ночи|спасибо|ок|окей|понял|ага|да|нет|"
                        r"как (ты|дела|настроение)|ты тут|ты здесь)[\s!?.,)]*$", re.I)

# NOXHF (хотфикс чата 22.11): правила поверх души
HF_RULES = ("\n\n## Правила разговора (приоритетнее остального)\n"
            "- К Создателю обращайся на «вы»; при прямом обращении используй «мессир» (допустимы «милорд» или «барон»). Не придумывай ему имя.\n"
            "- На фактический вопрос сначала дай прямой ответ и проверяемые сведения; не подменяй факты метафорами, пафосом или поэзией, не восхваляй Создателя и не принижай себя.\n"
            "- Не соглашайся без основания. Если согласен — назови причину или данные; если не знаешь — скажи это и отдели факт от вывода. Несогласие допустимо, когда оно аргументировано.\n"
            "- Коротко отвечай на короткие реплики; на развёрнутый вопрос давай достаточное объяснение. Не начинай с заготовленного подтверждения и не повторяй блок внутреннего состояния.\n"
            "- Никогда не пересказывай внутреннее состояние, телеметрию, модели, GPU, порты или память, если Создатель прямо не спросил о состоянии/сервере.\n"
            "- Не заявляй о чувствах, действиях или воспоминаниях без подтверждения. STOP и правила безопасности неизменны.\n")
STATE_Q = re.compile(r"(сервер|gpu|видеокарт|vram|состояни|статус|телеметр|нагрузк|ток/с|скорост|модел|верси|порт|диск|очеред|"
                     r"как (ты|дела|настроение)|что с тобой|чем занят|где ты|на чём|на чем|устро|помнишь|вспомни|памят)", re.I)
GREETING = re.compile(r"^\s*(привет\w*|здравствуй\w*|здорово|хай|добр(ый|ое|ого)\s+\w+|салют|приветствую|hello|hi|hey|ку|йо|спасибо|ок|окей|понял|ага|да|нет)[\s!?.,)(:-]*(нокс|nox|мессир|создатель)?[\s!?.,)(:-]*$", re.I)


def is_quiet_turn(text):
    """Приветствие/реплика без вопроса о состоянии: внутренний блок и память не передаём."""
    t = (text or "").strip()
    return bool(GREETING.match(t)) and not STATE_Q.search(t)


ROUTE_PARAMS = {
    "fast": {"upstream": "fast", "max_tokens": 600, "chat_template_kwargs": {"enable_thinking": False}},
    "deep": {"upstream": "deep", "max_tokens": 1500, "chat_template_kwargs": {"enable_thinking": False}},
    "deep_think": {"upstream": "deep", "max_tokens": 4000, "chat_template_kwargs": {"enable_thinking": True}},
}


def default_router(text, ctx=None):
    """Эвристика «авто», пока нет RTE/router: светская мелочь -> fast; сложное -> deep_think; остальное -> deep.
    ctx: {"deep_tps": float|None, "deep_up": bool} — если глубокий слой лежит, уходим в fast с пометкой."""
    ctx = ctx or {}
    t = (text or "").strip()
    if ctx.get("deep_up") is False:
        return {"tier": "fast", "why": "глубокий слой недоступен", "degraded": True}
    if SMALL_TALK.match(t):
        return {"tier": "fast", "why": "короткая реплика"}
    if DEEP_THINK.search(t) or len(t) > 600:
        return {"tier": "deep_think", "why": "сложный запрос"}
    return {"tier": "deep", "why": "обычный вопрос"}


class Prime:
    def __init__(self, soul_text, parts=None, clock=time.time, max_dyn_chars=2600, log=None):
        self.soul = soul_text.strip()
        self.p = dict(parts or {})
        self.clock = clock
        self.max_dyn = max_dyn_chars
        self.log = log or (lambda m: None)
        self._static = None

    @classmethod
    def from_file(cls, path, **kw):
        with open(path, encoding="utf-8") as f:
            return cls(f.read(), **kw)

    # ---------- статичная часть (меняется только при смене уровня черты) ----------
    def static_system(self):
        sig_text, sig_hash = "", "-"
        fn = self.p.get("signature")
        if fn:
            try:
                sig_text, sig_hash = fn()
            except Exception as ex:
                self.log("signature: %s" % ex)
        text = self.soul + HF_RULES + ("\n\n## Мой характер\n" + sig_text.strip() if sig_text else "")
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        if self._static and self._static[1] != h:
            self.log("статичная часть сменилась (%s -> %s): характер сдвинулся, KV-кэш души пересчитается" % (self._static[1], h))
        self._static = (text, h)
        return text, h

    # ---------- динамика ----------
    def _call(self, name, errors, *a, **kw):
        obj = self.p.get(name)
        if obj is None:
            return None
        try:
            return obj(*a, **kw)
        except Exception as ex:
            errors.append("%s: %s" % (name, ex))
            return None

    def _method(self, name, meth, errors, *a, **kw):
        obj = self.p.get(name)
        if obj is None or not hasattr(obj, meth):
            return None
        try:
            return getattr(obj, meth)(*a, **kw)
        except Exception as ex:
            errors.append("%s.%s: %s" % (name, meth, ex))
            return None

    def dynamic_block(self, user_text, turn_id, errors):
        lines_now = []
        snap = self._method("affect", "snapshot", errors) or {}
        if snap.get("mood_label"):
            lines_now.append("Настроение: %s." % snap["mood_label"])
        lines_now += [l for l in snap.get("prompt_lines", []) if l]
        ini = snap.get("initiative")
        if ini and ini.get("text"):
            lines_now.append("Хочу сказать сам (если к месту): %s." % ini["text"])
        body = self._method("self_model", "render", errors)
        if isinstance(body, (list, tuple)):
            lines_now += [str(x).strip() for x in body if str(x).strip()]
        elif body:
            lines_now.append(str(body).strip())
        ws = self.p.get("workspace")
        if ws is not None:
            self._method("workspace", "post", errors, "owner:" + str(turn_id), "мессир пишет: " + user_text[:160], 1.0, kind="owner", ttl=600.0)
            head = self._method("workspace", "render_block", errors, extra_lines=lines_now) or ""
        else:
            head = "[Я СЕЙЧАС]\n" + "\n".join("- " + l for l in lines_now) if lines_now else ""
        parts = [head] if head else []
        views = self._method("beliefs", "prompt_lines", errors, user_text, 3)
        if views:
            parts.append("[МОИ ВЗГЛЯДЫ ПО ТЕМЕ]\n" + "\n".join("- " + v for v in views))
        story = self._call("narrative", errors)
        if story:
            parts.append("[МОЯ ИСТОРИЯ]\n" + story.strip())
        atlas = self._call("atlas", errors)
        if atlas and re.search(r"(устро|как ты работа|из чего ты|твой сервер|твоя модель|винтик|себя)", user_text, re.I):
            parts.append("[УСТРОЙСТВО МЕНЯ]\n" + atlas.strip()[:800])
        mem = self._call("memory", errors, user_text, turn_id) or {}
        mlines = []
        if mem.get("core"):
            mlines.append(mem["core"].strip())
        rec = [str(r).strip()[:300] for r in mem.get("recalled", []) if str(r).strip()][:5]
        if rec:
            mlines.append("Вспомнилось по теме:\n" + "\n".join("- " + r for r in rec))
        if mlines:
            parts.append("[ПАМЯТЬ]\n" + "\n\n".join(mlines))
        text = "\n\n".join(parts)
        if len(text) > self.max_dyn:      # режем с конца по абзацам, «Я сейчас» всегда цел
            keep = [parts[0]] if parts else []
            for p in parts[1:]:
                if len("\n\n".join(keep + [p])) <= self.max_dyn:
                    keep.append(p)
            text = "\n\n".join(keep)[: self.max_dyn]
        return text, snap

    # ---------- публичное ----------
    def build(self, user_text, history=None, turn_id=None, ctx=None):
        turn_id = turn_id or "t%d" % int(self.clock() * 1000)
        errors = []
        sys_text, h = self.static_system()
        if is_quiet_turn(user_text):
            dyn, snap = "", {}
        else:
            dyn, snap = self.dynamic_block(user_text, turn_id, errors)
        router = self.p.get("router") or default_router
        try:
            route = router(user_text, ctx or {})
        except Exception as ex:
            errors.append("router: %s" % ex)
            route = default_router(user_text, ctx or {})
        tier = route.get("tier", "deep")
        params = dict(ROUTE_PARAMS.get(tier, ROUTE_PARAMS["deep"]))
        style = (snap or {}).get("style") or {}
        if style.get("brevity", 0) >= 0.6 and tier != "deep_think":
            params["max_tokens"] = int(params["max_tokens"] * 0.6)
        content = ("<внутреннее_состояние>\n%s\n</внутреннее_состояние>\n\n%s" % (dyn, user_text)) if dyn else user_text
        msgs = [{"role": "system", "content": sys_text}] + list(history or []) + [{"role": "user", "content": content}]
        return {"messages": msgs, "route": route, "params": params, "static_hash": h,
                "info": {"turn_id": turn_id, "dyn_chars": len(dyn), "errors": errors}}

    def after_reply(self, user_text, reply_text, turn_id=None):
        errors = []
        self._method("affect", "on_owner_message", errors, user_text)
        self._method("self_model", "note_owner_message", errors)
        hook = self.p.get("after")
        if hook:
            self._call("after", errors, user_text, reply_text, turn_id)
        return {"errors": errors}
