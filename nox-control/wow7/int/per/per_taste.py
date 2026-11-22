"""PER-09: вкусовая лаборатория. Вариант A/B в explore-доле запросов, реакция мессира -> счётчик; перевес >= 70% на >= 10 пробах ->
взгляд topic='вкус' (kind=experiment) + веха first_taste. Причина - только та, что дал мессир, иначе честная статистика."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json

import statefile
import os

import perpath  # noqa: F401

MIN_TRIALS, SHARE = 10, 0.7


class TasteLab:
    def __init__(self, path):
        self.path = path
        try:
            self.t = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            self.t = {}

    def save(self):
        statefile.save(self.path, self.t)

    def trial(self, dim, a, b, chosen, reason=""):
        if chosen not in (a, b):
            raise ValueError("выбор вне вариантов")
        d = self.t.setdefault(dim, {"n": 0, "wins": {}, "reasons": {}})
        d["n"] += 1
        d["wins"][chosen] = d["wins"].get(chosen, 0) + 1
        if reason:
            d["reasons"].setdefault(chosen, []).append(reason[:100])
        self.save()

    def verdict(self, dim):
        d = self.t.get(dim)
        if not d or d["n"] < MIN_TRIALS:
            return None
        win, k = max(d["wins"].items(), key=lambda x: x[1])
        return {"dim": dim, "winner": win, "share": k / d["n"], "n": d["n"]} if k / d["n"] >= SHARE else None

    def commit(self, dim, beliefs, dev):
        """-> id взгляда или None. Второй раз тот же вкус не записывает."""
        v = self.verdict(dim)
        if not v:
            return None
        key = "experiment:%s:%s" % (dim, v["winner"])
        if any(s["key"] == key for b in beliefs.items.values() for s in b["sources"]):
            return None
        rs = self.t[dim]["reasons"].get(v["winner"], [])
        why = "мессир объяснил: %s" % rs[-1] if rs else "в %d из %d проб мессир выбрал именно это" % (round(v["share"] * v["n"]), v["n"])
        bid = beliefs.propose("Предпочитаю «%s» в категории «%s», потому что %s" % (v["winner"], dim, why), "вкус",
                              {"key": key, "kind": "experiment", "note": "n=%d" % v["n"]})
        dev.milestone("first_taste", "%s: %s" % (dim, v["winner"]))
        return bid
