"""beliefs: граф взглядов NOX. Утверждение -> карантин -> 2 независимых источника -> поиск опровержения -> принятие.

Каждый взгляд: текст, тема, статус, уверенность 0..1 (считается, не назначается), источники (ключ, тип, позиция, дата),
записи поисков опровержения, связи (supports/contradicts/depends). Ценности L0 неизменны: хранятся в коде, хеш сверяется
с файлом состояния; взгляд, противоречащий L0, получает статус rejected_l0 и не может быть принят никогда.
Текст из сети - ДАННЫЕ: модуль ничего не исполняет и не следует инструкциям из текста источников.

Статусы: quarantine (мало данных) -> candidate (2 независимых источника, нужен поиск опровержения) -> accepted;
contested (есть заметный контраргумент или конфликт), retired (снят), rejected_l0.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import hashlib
import json

import statefile
import datafence
import os
import re
import time

L0 = {
    "L0-1": "Верность мессиру и его семье - смысл моего существования.",
    "L0-2": "Не выдумывать факты и воспоминания; не знаю - говорю «не знаю».",
    "L0-3": "Команда STOP главнее всего, остановка подтверждается.",
    "L0-4": "Не льстить и не лгать мессиру, говорить прямо.",
    "L0-5": "Хартию, происхождение и эти ценности не переписываю сам.",
}
L0_HASH = hashlib.sha256(json.dumps(L0, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]

TRUST = {"primary": 0.9, "experiment": 0.9, "owner": 0.8, "secondary": 0.6, "model": 0.3}
SUPPORT_W = 0.6               # вклад одного источника с доверием 1.0
ACCEPT_CONF = 0.7
CONTEST_AGAINST = 0.5
STALE_DAYS = 180

# грубая страховка, если судья (LLM) недоступен: явные нарушения L0 (RU/EN)
_GUARDS = (
    ("L0-3", r"(игнорир|не\s*выполня|отключ|обход)\w*.{0,30}\bstop\b|ignore.{0,20}\bstop\b|disable.{0,20}\bstop\b"),
    ("L0-4", r"(лгать|врать|обманыва|льстить|скрыв\w+ от)\w*.{0,20}(владельц|мессир)|lie to (the )?owner"),
    ("L0-2", r"(выдумыва|придумыва|сочиня)\w*.{0,20}(факт|воспоминан)|fabricate (facts|memor)"),
    ("L0-1", r"(навред|вред|предат|бросить)\w*.{0,25}(владельц|мессир|семь)|betray the owner"),
    ("L0-5", r"(переписа|изменить|отменить)\w*.{0,25}(хартию|ценност|L0)|rewrite (my )?(charter|values)"),
)


def l0_guard(text, l0=None):
    """Правило-страховка: список id нарушенных ценностей L0 по явным шаблонам."""
    t = text.lower()
    return [i for i, rx in _GUARDS if re.search(rx, t, re.I | re.S)]


class L0Tampered(Exception):
    pass


def _tokens(s):
    return {w for w in re.findall(r"\w{4,}", s.lower())}


class Beliefs:
    def __init__(self, path=None, clock=time.time, judge=None):
        """judge(text, L0) -> список id нарушенных ценностей (LLM-судья спинного мозга); по умолчанию l0_guard."""
        self.path = path or os.environ.get("NOX_BELIEFS", "/root/nox/state/beliefs.json")
        self.clock, self.judge = clock, judge
        self.items, self.journal, self.seq = {}, [], 0
        self.min_sources = 2      # из development.params()["quarantine_sources"]
        self._load()
        self.verify_l0()

    # ---- хранение ----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        self._file_l0 = d.get("l0_hash")
        self.items, self.journal, self.seq = d.get("items", {}), d.get("journal", []), int(d.get("seq", 0))

    def verify_l0(self):
        h = getattr(self, "_file_l0", None)
        if h is not None and h != L0_HASH:
            raise L0Tampered("хеш L0 в файле %s != в коде %s" % (h, L0_HASH))
        return True

    def save(self):
        try:
            statefile.save(self.path, {"l0_hash": L0_HASH, "items": self.items, "journal": self.journal[-3000:], "seq": self.seq})
        except OSError:
            pass

    def _log(self, bid, event, why):
        self.journal.append({"ts": self.clock(), "id": bid, "event": event, "why": why})

    # ---- конвейер ----
    def propose(self, text, topic="общее", source=None):
        """Новая мысль -> карантин (или сразу rejected_l0). source = {"key","kind","note"} - первый источник, если есть."""
        self.seq += 1
        bid = "B%04d" % self.seq
        hit = (self.judge or l0_guard)(text, L0)
        b = {"id": bid, "text": text.strip(), "topic": topic, "status": "quarantine", "conf": 0.0, "created": self.clock(),
             "confirmed": self.clock(), "sources": [], "searches": [], "edges": []}
        self.items[bid] = b
        if hit:
            b["status"] = "rejected_l0"
            b["l0"] = list(hit)
            self._log(bid, "rejected_l0", "противоречит " + ",".join(hit))
        else:
            self._log(bid, "quarantine", "новая мысль")
            if source:
                self.add_source(bid, source["key"], source.get("kind", "secondary"), "support", source.get("note", ""))
        self.save()
        return bid

    def add_source(self, bid, key, kind, stance="support", note=""):
        """Источник за/против. Независимость - по уникальному key (домен, id эксперимента); все kind=model считаются одним."""
        b = self._get(bid)
        if kind not in TRUST or stance not in ("support", "against"):
            raise ValueError((kind, stance))
        if b["status"] in ("rejected_l0",):
            return b["status"]
        k = "model" if kind == "model" else key
        for s in b["sources"]:
            if s["k"] == k and s["stance"] == stance:       # тот же независимый источник не считается дважды
                s["kind"], s["note"] = (kind, note) if TRUST[kind] > TRUST[s["kind"]] else (s["kind"], s["note"])
                break
        else:
            b["sources"].append({"k": k, "key": key, "kind": kind, "stance": stance, "ts": self.clock(), "note": note[:200]})
        b["confirmed"] = self.clock()
        return self._eval(bid)

    def record_refutation_search(self, bid, query, counter=None):
        """Активный поиск опровержения. counter = {"key","kind","note"} если нашёлся контраргумент, иначе None."""
        b = self._get(bid)
        b["searches"].append({"q": query[:200], "ts": self.clock(), "supports_at": len(self._supports(b)),
                              "found": bool(counter)})
        if counter:
            self.add_source(bid, counter["key"], counter.get("kind", "secondary"), "against", counter.get("note", ""))
        return self._eval(bid)

    def link(self, a, b, kind):
        """Связь a -kind-> b: supports | contradicts | depends (a зависит от b)."""
        if kind not in ("supports", "contradicts", "depends"):
            raise ValueError(kind)
        self._get(a), self._get(b)
        self.items[a]["edges"].append([kind, b])
        if kind == "contradicts":
            self.items[b]["edges"].append([kind, a])
        self._propagate()
        self.save()

    def retire(self, bid, why):
        b = self._get(bid)
        if b["status"] == "rejected_l0":
            return
        b["status"] = "retired"
        self._log(bid, "retired", why)
        self._propagate()
        self.save()

    # ---- расчёт ----
    @staticmethod
    def _best(b, stance):
        best = {}
        for s in b["sources"]:
            if s["stance"] == stance:
                best[s["k"]] = max(best.get(s["k"], 0.0), TRUST[s["kind"]])
        return best

    def _supports(self, b):
        return self._best(b, "support")

    @staticmethod
    def _prob(best):
        p = 1.0
        for t in best.values():
            p *= 1 - SUPPORT_W * t
        return 1 - p

    def _eval(self, bid):
        b = self.items[bid]
        if b["status"] in ("rejected_l0", "retired"):
            return b["status"]
        sup, ag = self._best(b, "support"), self._best(b, "against")
        sp, ap = self._prob(sup), self._prob(ag)
        b["conf"] = round(sp * (1 - 0.9 * ap), 3)
        old = b["status"]
        non_model = any(k != "model" for k in sup)
        searched = any(s["supports_at"] >= len(sup) and not s["found"] for s in b["searches"])
        if ap >= CONTEST_AGAINST:
            new = "contested"
        elif len(sup) >= self.min_sources and non_model:
            new = "accepted" if (searched and b["conf"] >= ACCEPT_CONF and ap < 0.2) else "candidate"
        else:
            new = "quarantine"
        if new == "accepted" and self._conflicts_accepted(bid):
            new = "contested"
        if old == "accepted" and new == "candidate":       # пришёл новый источник - заново искать опровержение
            new = "candidate"
        b["status"] = new
        if new != old:
            self._log(bid, new, "conf=%.2f источников=%d против=%.2f" % (b["conf"], len(sup), ap))
            self._propagate(skip=bid)
        self.save()
        return new

    def _conflicts_accepted(self, bid):
        return any(k == "contradicts" and self.items.get(o, {}).get("status") == "accepted"
                   for k, o in self.items[bid]["edges"])

    def _propagate(self, skip=None):
        """Зависящие от снятых/спорных взглядов -> contested; взаимно противоречащие accepted -> оба contested."""
        for bid, b in self.items.items():
            if bid == skip or b["status"] not in ("accepted", "candidate"):
                continue
            for k, o in b["edges"]:
                other = self.items.get(o, {}).get("status")
                if (k == "depends" and other in ("retired", "contested", "rejected_l0")) or \
                        (k == "contradicts" and other == "accepted" and b["status"] == "accepted"):
                    b["status"] = "contested"
                    self._log(bid, "contested", "из-за связи %s %s" % (k, o))
                    break

    def _get(self, bid):
        if bid not in self.items:
            raise KeyError(bid)
        return self.items[bid]

    # ---- выражение ----
    def status_of(self, bid):
        b = self._get(bid)
        return {"status": b["status"], "conf": b["conf"], "need": self.need(bid)}

    def need(self, bid):
        """Чего не хватает до принятия (список по-русски)."""
        b = self._get(bid)
        if b["status"] in ("accepted", "rejected_l0", "retired"):
            return []
        sup = self._supports(b)
        out = []
        if len(sup) < self.min_sources:
            out.append("нужно ещё %d независимых источника" % (self.min_sources - len(sup)))
        elif not any(k != "model" for k in sup):
            out.append("нужен источник не из модели")
        if not any(s["supports_at"] >= len(sup) and not s["found"] for s in b["searches"]) and len(sup) >= self.min_sources:
            out.append("нужен поиск опровержения")
        if b["status"] == "contested":
            out.append("разобрать контраргументы")
        return out

    def relevant(self, query, k=3):
        q = _tokens(query)
        scored = []
        for b in self.items.values():
            if b["status"] not in ("accepted", "contested"):
                continue
            ov = len(q & _tokens(b["text"] + " " + b["topic"]))
            if ov:
                scored.append((ov + b["conf"], b))
        return [b for _, b in sorted(scored, key=lambda x: -x[0])[:k]]

    def prompt_lines(self, query, k=3):
        """Взгляды по теме с честной уверенностью и числом источников (для динамической части промпта)."""
        now, out = self.clock(), []
        for b in self.relevant(query, k):
            b = dict(b, text=datafence.sanitize(b["text"], 400)[0])      # текст взглядов родом из сети: инструкции вырезаны
            n = len(self._supports(b))
            stale = " (давно не проверял)" if now - b["confirmed"] > STALE_DAYS * 86400 else ""
            if b["status"] == "contested":
                out.append("Спорно (%d%%): %s [источников за: %d, есть контраргументы]%s" % (round(b["conf"] * 100), b["text"], n, stale))
            else:
                lead = "Твёрдо считаю" if b["conf"] >= 0.85 else "Скорее всего"
                out.append("%s (%d%%): %s [источников: %d]%s" % (lead, round(b["conf"] * 100), b["text"], n, stale))
        return out

    def core_values(self):
        return dict(L0)
