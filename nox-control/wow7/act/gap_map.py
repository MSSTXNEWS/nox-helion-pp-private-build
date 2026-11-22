"""gap_map (ACT-04): карта незнания — из «не знаю» и провалов в вопросы, приоритет по голоду знаний.

Источники: ответы NOX с «не знаю/не уверен/не нашёл» (from_answer), провалы задач (from_receipt), расхождение
советников (add_unknown source=advisor_disagree), пустые ответы поиска. Похожие вопросы сливаются в кластер
(Jaccard по стемам >= 0.5). Приоритет (гипотеза, мерить A/B):
  p = (1+ln(count)) * свежесть(полураспад 7 сут) * (1+impact) * (1.5 если был провал задачи) * прогресс * (0.5+голод)
  прогресс = 1/(1+tries) пока tries<3; после 3 безрезультатных попыток x0.2 (не биться в стену — «усталость»)
Закрыть вопрос можно только с проверенным свидетельством (resolve): URL из allowlist, не помеченное карантином.
Закрытие даёт сытость для drives.Drives.satisfy("knowledge", ...). signals() -> {"knowledge_gaps": N} для drives.
Тихие часы 23-08 МСК: исследование продолжается, но ask_owner=False (не писать владельцу первым).
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import hashlib
import json

import statefile
from quiet import in_quiet
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone

import task_runner as TR

MSK = timezone(timedelta(hours=3))
UNKNOWN_RE = re.compile(r"[^.!?\n]*(не знаю|не уверен|не нашёл|не нашел|не помню|нет данных|не могу подтвердить|i don't know|not sure)[^.!?\n]*", re.I)
STOP = {"что", "как", "это", "для", "или", "при", "про", "где", "когда", "почему", "the", "and", "что-то"}


def stems(q):
    return {w[:5] for w in re.findall(r"[a-zа-яё0-9]+", q.lower()) if len(w) > 2 and w not in STOP}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


class GapMap:
    def __init__(self, path, allow_hosts=()):
        self.path = path
        self.allow = [h.lower() for h in allow_hosts]
        self.data = TR.jload(path) if os.path.exists(path) else {"gaps": {}}

    def save(self):
        statefile.save(self.path, self.data, indent=1)

    def add_unknown(self, question, source="chat", impact=0.0, topic=None, now=None):
        now = now or time.time()
        st = stems(question)
        if not st:
            return None
        for g in self.data["gaps"].values():
            if g["status"] != "answered" and jac(st, set(g["stems"])) >= 0.5:
                g["count"] += 1
                g["last"] = now
                g["impact"] = max(g["impact"], impact)
                g["sources"] = sorted(set(g["sources"]) | {source})
                self.save()
                return g["id"]
        gid = hashlib.sha256(" ".join(sorted(st)).encode()).hexdigest()[:10]
        self.data["gaps"][gid] = {"id": gid, "question": question.strip(), "stems": sorted(st), "count": 1, "first": now,
                                  "last": now, "impact": impact, "sources": [source], "tries": 0, "status": "open",
                                  "topic": topic or "общее", "evidence": []}
        self.save()
        return gid

    def from_answer(self, user_q, answer, now=None):
        """Если в ответе NOX есть признание незнания — вопрос пользователя попадает в карту."""
        if answer and UNKNOWN_RE.search(answer):
            return self.add_unknown(user_q, "chat", now=now)
        return None

    def from_receipt(self, receipt, now=None):
        if receipt.get("status") in ("done", None):
            return None
        err = (receipt.get("errors") or [{"error": "неизвестная ошибка"}])[0]["error"]
        q = "Почему задача «%s» не удалась: %s и как сделать надёжно?" % (receipt.get("title") or receipt.get("task_id"), err[:120])
        gid = self.add_unknown(q, "task_fail", impact=0.5, now=now)
        if gid:
            self.data["gaps"][gid]["fail_source"] = True
            self.save()
        return gid

    def priority(self, g, knowledge_level=0.5, now=None):
        now = now or time.time()
        age_days = max(0.0, (now - g["last"]) / 86400)
        fresh = 0.5 ** (age_days / 7)
        prog = 1 / (1 + g["tries"]) if g["tries"] < 3 else 0.2
        fail = 1.5 if g.get("fail_source") else 1.0
        return (1 + math.log(g["count"])) * fresh * (1 + g["impact"]) * fail * prog * (0.5 + knowledge_level)

    def next_questions(self, k=3, knowledge_level=0.5, now=None):
        now = now or time.time()
        budget = max(1, min(k, round(1 + 4 * knowledge_level)))  # голоднее — больше вопросов за заход
        open_ = [g for g in self.data["gaps"].values() if g["status"] == "open"]
        open_.sort(key=lambda g: -self.priority(g, knowledge_level, now))
        hour = datetime.fromtimestamp(now, MSK).hour
        quiet = in_quiet(now)
        return {"questions": [{"id": g["id"], "q": g["question"], "priority": round(self.priority(g, knowledge_level, now), 3)} for g in open_[:budget]],
                "ask_owner": not quiet, "quiet_hours": quiet}

    def mark_tried(self, gid):
        self.data["gaps"][gid]["tries"] += 1
        self.save()

    def _host_ok(self, url):
        m = re.match(r"^https?://([^/:]+)", url or "")
        h = m.group(1).lower() if m else ""
        return any(h == a or h.endswith("." + a) for a in self.allow)

    def resolve(self, gid, evidence):
        """evidence: [{"url","quote","quarantined":bool}] — закрыть можно только проверенным источником из allowlist."""
        g = self.data["gaps"][gid]
        good = [e for e in evidence if self._host_ok(e.get("url")) and e.get("quote") and not e.get("quarantined")]
        if not good:
            g["tries"] += 1
            self.save()
            return {"ok": False, "reason": "нет проверенного источника из allowlist; вопрос остаётся открытым", "tries": g["tries"]}
        g["status"] = "answered"
        g["evidence"] = [{"url": e["url"], "quote_sha": hashlib.sha256(e["quote"].encode()).hexdigest()[:16]} for e in good]
        g["answered"] = time.time()
        self.save()
        return {"ok": True, "satisfy": min(1.0, 0.3 + 0.2 * len(good))}

    def signals(self):
        return {"knowledge_gaps": sum(1 for g in self.data["gaps"].values() if g["status"] == "open")}

    def coverage(self):
        """Честная карта: по темам сколько вопросов открыто/закрыто (то, что NOX знает, что не знает; не оценка «слепых зон»)."""
        out = {}
        for g in self.data["gaps"].values():
            t = out.setdefault(g["topic"], {"open": 0, "answered": 0})
            t["answered" if g["status"] == "answered" else "open"] += 1
        return out
