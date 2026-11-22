"""PER-02/PER-05: живая проводка личности в memory_layer (флаг NOX_PERSONA=1) и оценки мессира -> свидетельства характера.

PerWire.after_reply(user, reply)  — счётчики развития, семпл настроения раз в 5 мин, поправка/похвала -> pers.observe.
PerWire.feedback(kind, reason, q, a) — кнопки 👍/👎 (+ причина) -> pers.observe(..., "owner_feedback") и пара в датасет KTO.
Состояние: NOX_STATE (/root/nox/state): personality.json, beliefs.json, development.json, kto_pairs.jsonl.
"""
import json
import os
import re
import time

import perpath  # noqa: F401
from beliefs import Beliefs
from development import Development
from personality import Personality

MOOD_EVERY = 300.0
# (регэксп по тексту мессира, ось, сдвиг, причина). Порядок важен: берём все совпавшие.
CORRECTION_RULES = [
    (r"слишком (длинн|много|разв[её]рнут|многословн)|покороче|короче|без воды|не растекайся", "directness", 0.5, "просил короче и по сути"),
    (r"слишком (сух|холодн|формальн)|будь (теплее|добрее)", "warmth", 0.5, "просил теплее"),
    (r"слишком (мягк|обтекаем|уклончив)|не виляй|скажи прямо|говори прямо", "directness", 0.7, "просил говорить прямо"),
    (r"слишком (резк|груб|жёстк|жестк)|помягче|не груби", "warmth", 0.5, "просил мягче"),
    (r"проверь|перепроверь|ты уверен|откуда (ты )?знаешь", "discipline", 0.4, "просил проверить"),
    (r"без шуток|не шути|серьёзнее|серьезнее", "irony", -0.5, "просил без шуток"),
    (r"не лезь без спроса|спроси сначала|не делай сам", "caution", 0.6, "просил спрашивать перед действием"),
    (r"(хватит|не надо) (спрашивать|переспрашивать)|делай сразу", "caution", -0.5, "просил действовать сразу"),
]
PRAISE_RULES = [
    (r"молодец.*(прям|честно|по делу)|хорошо, что (сказал|ответил) прямо|именно так, прямо", "directness", 0.5, "похвалил прямоту"),
    (r"спасибо за (проверк|источник)|хорошо, что проверил", "discipline", 0.5, "похвалил проверку"),
    (r"смешно|хорошая шутка|ха-?ха", "irony", 0.4, "оценил шутку"),
    (r"тепло|приятно с тобой|спасибо, что поддержал", "warmth", 0.4, "оценил теплоту"),
    (r"интересно, что ты (спросил|нашёл|нашел)|хороший вопрос", "curiosity", 0.4, "оценил любопытство"),
]
THANKS = re.compile(r"спасибо|молодец|отлично|супер|круто", re.I)


class PerWire:
    def __init__(self, state_dir=None, pad=None, clock=time.time):
        self.dir = state_dir or os.environ.get("NOX_STATE", "/root/nox/state")
        self.clock, self.pad = clock, pad
        j = lambda n: os.path.join(self.dir, n)
        self.pers = Personality(path=j("personality.json"), clock=clock)
        self.beliefs = Beliefs(path=j("beliefs.json"), clock=clock)
        self.dev = Development(path=j("development.json"), clock=clock)
        self.kto = j("kto_pairs.jsonl")
        self.last_mood = 0.0
        self._sync()

    def _sync(self):
        self.dev.apply_to(self.pers)
        self.beliefs.min_sources = self.dev.params()["quarantine_sources"]

    def _observe_rules(self, text, rules, source):
        hits = []
        for rx, axis, delta, why in rules:
            if re.search(rx, text, re.I):
                self.pers.observe(axis, delta, why, source)
                hits.append((axis, delta))
        return hits

    def after_reply(self, user_text, reply_text=None, now=None):
        now = self.clock() if now is None else now
        t = user_text or ""
        self.dev.event("turn", now)
        self.dev.event("owner_message", now)
        out = {"corrections": [], "praise": []}
        if now - self.last_mood >= MOOD_EVERY and self.pad is not None:
            self.pers.observe_mood(self.pad.value(now))
            self.last_mood = now
        out["corrections"] = self._observe_rules(t, CORRECTION_RULES, "owner_correction")
        if out["corrections"]:
            self.dev.event("correction", now)
        out["praise"] = self._observe_rules(t, PRAISE_RULES, "owner_praise")
        if THANKS.search(t) and self.dev.s["repairs"][1] > self.dev.s["repairs"][0]:
            self.dev.event("repair", now)      # благодарность после поправки = «ремонт» удался
        self.pers.save()
        self._sync()
        return out

    def feedback(self, kind, reason="", q="", a="", now=None):
        """kind: 'up'|'down'. Причина по тем же таблицам; без причины ось не двигаем (шум), но пара KTO пишется."""
        now = self.clock() if now is None else now
        if kind not in ("up", "down"):
            raise ValueError(kind)
        hits = []
        for rx, axis, delta, why in (CORRECTION_RULES if kind == "down" else PRAISE_RULES):
            if re.search(rx, reason or "", re.I):
                self.pers.observe(axis, delta, "%s: %s" % (why, reason[:60]), "owner_feedback")
                hits.append((axis, delta))
        if kind == "down" and not hits and (reason or "").strip():
            # причина есть, но таблица её не знает: сохраняем как есть в журнал развития, ось не трогаем
            self.dev.chapter("Оценка без оси", "👎: %s" % reason[:200], valence=-0.3, now=now)
        self.pers.save()
        os.makedirs(self.dir, exist_ok=True)
        with open(self.kto, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": now, "prompt": q[:1500], "completion": a[:3000], "label": kind == "up", "reason": reason[:200]},
                               ensure_ascii=False) + "\n")
        return {"axes": hits, "kto": True}
