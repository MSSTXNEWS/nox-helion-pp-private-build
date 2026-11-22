"""ДЕЙСТВИЕ: команды с превью -> подтверждение -> выполнение -> квитанция (одна строка результата).
Встроено: удаление прошлых запросов (превью всегда, мягкое удаление, undo 10 мин). Планировщики подключаются через core.planners:
  planner.kind, planner.match(text)->plan|None, planner.preview(plan)->str, planner.irreversible(plan)->bool, async planner.execute(plan)->str
TaskRunnerPlanner оборачивает ACT/task_runner.Runner (карточка -> submit/run/receipt)."""
import asyncio
import os
import re
import secrets
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


class ActionReason(Exec):
    name, budget_s = "reason", 15.0

    async def run(self, st):
        it, core = st.intent, self.core
        pend = st.conv.pending
        if it == "deny":
            st.conv.pending = None
            st.draft = "Хорошо, ничего не меняю."
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
