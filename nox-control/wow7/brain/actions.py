"""ДЕЙСТВИЕ: команды с превью -> подтверждение -> выполнение -> квитанция (одна строка результата).
Встроено: удаление прошлых запросов (превью всегда, мягкое удаление, undo 10 мин). Планировщики подключаются через core.planners:
  planner.kind, planner.match(text)->plan|None, planner.preview(plan)->str, planner.irreversible(plan)->bool, async planner.execute(plan)->str
TaskRunnerPlanner оборачивает ACT/task_runner.Runner (карточка -> submit/run/receipt)."""
import asyncio
import json
import os
import re
import secrets
import tempfile
import time

from executors import Exec, NUMW

CONFIRM_TTL, UNDO_TTL = 120.0, 600.0


def parse_count(text, total):
    t = text.lower()
    if re.search(r"\bвс[еёе]\b", t):
        return total
    m = re.search(r"\b(\d+)\b", t)
    if m:
        return max(1, int(m.group(1)))
    for w, n in NUMW.items():
        if re.search(r"\b%s\w*\b" % w, t):
            return n
    return 1


def _hm(ts):
    return time.strftime("%H:%M", time.localtime(ts)) if ts else "--:--"




ANSWER_SETTINGS_REQUEST_RE = re.compile(
    r"(?:настройк\w*\s+ответ\w*|длин[ауы]\s+ответ\w*|режим\s+(?:авто|быстр\w*|глубок\w*|fast|deep)|"
    r"верни\w*\s+(?:всё\s+)?по\s+умолчанию|сброси\w*\s+настройк\w*)",
    re.I,
)
ANSWER_SETTINGS_DEFAULTS = {"max_tokens": 1500, "mode": "auto"}


class AnswerSettings:
    """Настройки длины и режима ответа на каждого speaker; defaults never imply a stored preference."""

    def __init__(self, core):
        self.core = core

    @staticmethod
    def is_request(text):
        return bool(ANSWER_SETTINGS_REQUEST_RE.search(text or ""))

    @property
    def path(self):
        state_dir = getattr(getattr(self.core, "cfg", None), "state_dir", None)
        return os.path.join(state_dir, "answer_settings.json") if state_dir else None

    def _load(self):
        path = self.path
        if not path:
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, speaker):
        key = str(speaker or "owner")[:120]
        value = self._load().get(key)
        if not isinstance(value, dict):
            return dict(ANSWER_SETTINGS_DEFAULTS), False
        try:
            max_tokens = int(value.get("max_tokens", ANSWER_SETTINGS_DEFAULTS["max_tokens"]))
        except (TypeError, ValueError):
            max_tokens = ANSWER_SETTINGS_DEFAULTS["max_tokens"]
        max_tokens = max(300, min(3000, max_tokens))
        mode = value.get("mode") if value.get("mode") in ("auto", "fast", "deep") else "auto"
        return {"max_tokens": max_tokens, "mode": mode}, True

    def _save(self, data):
        path = self.path
        if not path:
            raise OSError("state_dir недоступен")
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".answer_settings.", suffix=".tmp", dir=directory, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, sort_keys=True)
                f.write("\n")
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def _mode_label(mode):
        return {"auto": "авто", "fast": "быстро", "deep": "глубоко"}.get(mode, "авто")

    def process(self, text, speaker):
        key = str(speaker or "owner")[:120]
        raw = text or ""
        data = self._load()
        current, stored = self.get(key)
        if re.search(r"верни\w*\s+(?:всё\s+)?по\s+умолчанию|сброси\w*\s+настройк\w*", raw, re.I):
            data.pop(key, None)
            try:
                self._save(data)
            except OSError as e:
                return "Мессир, не удалось сохранить настройки по умолчанию: %s." % type(e).__name__
            return "Настройки ответа возвращены к значениям по умолчанию: 1500 токенов, режим — авто."
        length_match = re.search(r"(?:max[_ -]?tokens|токен\w*|длин\w*|ответ\w*)\D{0,24}(\d{2,5})", raw, re.I)
        if length_match is None:
            length_match = re.search(r"\b(\d{3,5})\s*(?:токен\w*)?\b", raw, re.I)
        mode = None
        if re.search(r"\b(?:авто|automatic)\b", raw, re.I):
            mode = "auto"
        elif re.search(r"\b(?:быстро|быстрый|быстрый\s+режим|fast)\b", raw, re.I):
            mode = "fast"
        elif re.search(r"\b(?:глубоко|глубокий|deep)\b", raw, re.I):
            mode = "deep"
        if length_match is None and mode is None:
            source = "сохранены" if stored else "не сохранены"
            return "Мессир, отдельные настройки ответа %s; действуют %d токенов и режим «%s»." % (
                source, current["max_tokens"], self._mode_label(current["mode"]))
        max_tokens = current["max_tokens"]
        if length_match is not None:
            requested = int(length_match.group(1))
            if not 300 <= requested <= 3000:
                return "Длина ответа должна быть от 300 до 3000 токенов; настройки не изменены."
            max_tokens = requested
        updated = {"max_tokens": max_tokens, "mode": mode or current["mode"]}
        data[key] = updated
        try:
            self._save(data)
        except OSError as e:
            return "Мессир, не удалось сохранить настройки: %s. Текущие значения не подтверждаю." % type(e).__name__
        return "Сохранено: %d токенов, режим «%s»." % (updated["max_tokens"], self._mode_label(updated["mode"]))

class ActionReason(Exec):
    name, budget_s = "reason", 15.0

    async def run(self, st):
        it, core = st.intent, self.core
        pend = st.conv.pending
        if it == "deny":
            st.conv.pending = None
            st.draft = "Хорошо, ничего не меняю."
        elif it == "answer_settings":
            st.draft = AnswerSettings(core).process(st.user_text, st.speaker)
        elif it == "undo":
            st.draft = self.undo(st)
        elif it == "confirm":
            st.draft = await self.confirm(st, pend)
        elif it == "delete_history":
            st.draft = self.preview_delete(st)
        elif st.action:
            planner, plan = st.action
            if planner.irreversible(plan):
                st.conv.pending = {"token": secrets.token_hex(3), "kind": planner.kind, "plan": plan, "until": time.time() + CONFIRM_TTL}
                st.draft = planner.preview(plan) + "\nПодтверждаешь - «да» или «нет»?"
            else:
                st.draft = await planner.execute(plan)
        st.final = st.draft
        st.turn.trace["action"] = {"intent": it, "pending": bool(st.conv.pending)}
        await st.turn.emit_text(st.draft)

    def degraded(self, st):
        st.draft = "Мессир, команду не выполнил: сбой в исполнителе действий. Ничего не изменено."
        st.final = st.draft
        st.conv.pending = None
        st.turn.parts.append(st.draft)

    # ---- удаление истории
    def preview_delete(self, st):
        conv = st.conv
        users = [m for m in conv.messages if m["role"] == "user" and not m.get("control")]
        if not users:
            return "Удалять нечего: прошлых запросов в этом диалоге нет."
        n = min(parse_count(st.user_text, len(users)), len(users))
        sel = users[-n:]
        ids = [m["turn_id"] for m in sel]
        conv.pending = {"token": secrets.token_hex(3), "kind": "delete_history", "turn_ids": ids, "until": time.time() + CONFIRM_TTL}
        lines = ["%d. «%s» (%s)" % (i, m["content"][:48].replace("\n", " "), _hm(m.get("ts"))) for i, m in enumerate(sel, 1)]
        return ("Удалить %d прошлых запрос(а) вместе с моими ответами на них?\n%s\nКопию держу %d мин: вернуть можно командой «верни удалённое». Подтверждаешь - «да» или «нет»?"
                % (n, "\n".join(lines), int(UNDO_TTL // 60)))

    async def confirm(self, st, pend):
        conv, core = st.conv, self.core
        st.conv.pending = None
        if pend["kind"] == "delete_history":
            ids = set(pend["turn_ids"])
            gone = [m for m in conv.messages if m.get("turn_id") in ids]
            conv.messages = [m for m in conv.messages if m.get("turn_id") not in ids]
            rid = "del-" + secrets.token_hex(3)
            conv.deleted.append({"receipt_id": rid, "msgs": gone, "until": time.time() + UNDO_TTL})
            left = [m for m in conv.messages if m.get("turn_id") in ids]       # проверка чтением
            q, a = sum(1 for m in gone if m["role"] == "user"), sum(1 for m in gone if m["role"] == "assistant")
            mem = core.organs.forget(sorted(ids))
            receipt = {"receipt_id": rid, "kind": "delete_history", "conversation_id": conv.id, "turn_ids": sorted(ids), "removed_requests": q,
                       "removed_answers": a, "verified_absent": not left, "remaining_messages": len(conv.messages), "memory": mem, "ts": time.time()}
            core.write_receipt("CORE-" + rid, receipt)
            st.turn.emit_meta("meta", {"receipt": receipt})
            tail = " Из памяти убрал записей: %s." % mem["revoked"] if isinstance(mem, dict) and mem.get("revoked") else ""
            if not receipt["verified_absent"]:
                return "Мессир, удаление не подтвердилось проверкой: часть реплик осталась. Квитанция %s, подробности в журнале." % rid
            return "Удалил %d запросов и %d моих ответов, проверил чтением: в диалоге осталось %d реплик.%s Квитанция %s; вернуть - «верни удалённое» в течение %d мин." % (
                q, a, len(conv.messages), tail, rid, int(UNDO_TTL // 60))
        planner = next((p for p in core.planners if p.kind == pend["kind"]), None)
        if not planner:
            return "Мессир, исполнитель этого действия сейчас не подключён, ничего не сделано."
        return await planner.execute(pend["plan"])

    def undo(self, st):
        now = time.time()
        rec = next((d for d in reversed(st.conv.deleted) if d["until"] > now and d["msgs"]), None)
        if not rec:
            return "Возвращать нечего: недавних удалений нет."
        st.conv.messages = sorted(st.conv.messages + rec["msgs"], key=lambda m: m.get("ts", 0))
        n = sum(1 for m in rec["msgs"] if m["role"] == "user")
        rec["msgs"] = []
        return "Вернул %d запросов с ответами (квитанция %s)." % (n, rec["receipt_id"])


class TaskRunnerPlanner:
    """card_builder(text)->card|None; необратимое определяется набором опасных операций."""
    kind = "task_runner"

    def __init__(self, runner, card_builder, irreversible_ops=("delete", "exec", "shell")):
        self.runner, self.build, self.bad = runner, card_builder, set(irreversible_ops)

    def match(self, text):
        return self.build(text)

    def irreversible(self, card):
        return any(s.get("op") in self.bad for s in card.get("steps", []))

    def preview(self, card):
        return "План «%s»:\n%s" % (card["id"], "\n".join("%d. %s %s" % (i, s["op"], s.get("args", {}).get("path", "")) for i, s in enumerate(card["steps"], 1)))

    async def execute(self, card):
        loop = asyncio.get_running_loop()
        r = await loop.run_in_executor(None, self.runner.submit, card)
        if not r.get("ok"):
            return "Мессир, задачу не принял: %s." % r.get("error", "ошибка карточки")
        run = await loop.run_in_executor(None, self.runner.run, r["id"])
        rec = await loop.run_in_executor(None, lambda: self.runner.receipt(r["id"], True))
        status = (run or {}).get("status") or (rec or {}).get("status", "?")
        return "Задача %s: статус %s, квитанция записана%s." % (r["id"], status, " (дубликат уже был)" if r.get("dup") else "")
