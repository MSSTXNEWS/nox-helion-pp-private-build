"""skills (ACT-03): библиотека навыков в духе Voyager — только ПРОВЕРЕННЫЕ карточки task_runner.

Навык = шаблон карточки с параметрами {{имя}} + описание + статистика исходов.
Принимается в библиотеку лишь если: (1) есть квитанция со status=done и live_verify.ok=True,
(2) шаблон проходит task_runner.validate_card после подстановки примера параметров,
(3) для задачи был успешный откат (receipt_rollback.status=rolled_back, verified) — навык обратим.
Иначе — в карантин (skills/_quarantine), в поиск не попадает.
Поиск: BM25 по имени/описанию/тегам (стемминг-префикс 5 символов для RU), без внешних зависимостей.
Навык с долей провалов >50% при >=4 запусков уходит на пенсию (retired) — не используется, но хранится.
"""
import hashlib
import json
import math
import os
import re
import time

import task_runner as TR

PLACE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,47}$")


def toks(s):
    return [w[:5] for w in re.findall(r"[a-zа-яё0-9]+", s.lower()) if len(w) > 1]


def _subst(o, params):
    if isinstance(o, str):
        m = PLACE.fullmatch(o.strip())
        if m:  # строка целиком — плейсхолдер: сохраняем тип значения
            return params[m.group(1)]
        return PLACE.sub(lambda m: str(params[m.group(1)]), o)
    if isinstance(o, list):
        return [_subst(x, params) for x in o]
    if isinstance(o, dict):
        return {k: _subst(v, params) for k, v in o.items()}
    return o


def placeholders(o):
    if isinstance(o, str):
        return set(PLACE.findall(o))
    if isinstance(o, list):
        return set().union(*[placeholders(x) for x in o]) if o else set()
    if isinstance(o, dict):
        return set().union(*[placeholders(v) for v in o.values()]) if o else set()
    return set()


class SkillError(ValueError):
    pass


class SkillLibrary:
    def __init__(self, root):
        self.root = root
        os.makedirs(os.path.join(root, "_quarantine"), exist_ok=True)

    def _p(self, name, q=False):
        return os.path.join(self.root, "_quarantine" if q else "", name + ".json")

    def _load(self, name):
        p = self._p(name)
        if not os.path.exists(p):
            raise SkillError("no such skill: " + name)
        return TR.jload(p)

    def _save(self, sk, q=False):
        TR.atomic_write(self._p(sk["name"], q), (json.dumps(sk, ensure_ascii=False, indent=1) + "\n").encode())

    # --- приём
    def add(self, name, description, template, example_params, receipt, rollback_receipt, tags=()):
        if not NAME_RE.match(name):
            raise SkillError("name must match %s" % NAME_RE.pattern)
        need = placeholders(template)
        if set(example_params) != need:
            raise SkillError("example_params must cover exactly the placeholders %s" % sorted(need))
        reasons = []
        if receipt.get("status") != "done" or not receipt.get("live_verify", {}).get("ok"):
            reasons.append("no verified successful run")
        if rollback_receipt.get("status") != "rolled_back" or not rollback_receipt.get("live_verify", {}).get("ok"):
            reasons.append("rollback not verified")
        try:
            TR.validate_card(_subst(template, example_params))
        except (TR.ActError, KeyError) as e:
            reasons.append("template invalid: %s" % e)
        sk = {"name": name, "description": description, "tags": list(tags), "template": template,
              "params": sorted(need), "example_params": example_params, "runs": 0, "fails": 0,
              "status": "active", "added": time.time(),
              "evidence": {"receipt": receipt.get("id"), "rollback_receipt": rollback_receipt.get("id"),
                           "journal_head": receipt.get("journal", {}).get("head")},
              "sha": hashlib.sha256(TR.canon(template).encode()).hexdigest()[:16]}
        if reasons:
            sk["status"] = "quarantine"
            sk["reasons"] = reasons
            self._save(sk, q=True)
            return {"ok": False, "quarantined": True, "reasons": reasons}
        for ex in self.list():
            if ex["sha"] == sk["sha"] and ex["name"] != name:
                return {"ok": False, "duplicate_of": ex["name"]}
        if os.path.exists(self._p(name)):
            old = self._load(name)
            sk["runs"], sk["fails"], sk["version"] = old["runs"], old["fails"], old.get("version", 1) + 1
        self._save(sk)
        return {"ok": True, "name": name}

    def list(self, include_retired=False):
        out = []
        for f in sorted(os.listdir(self.root)):
            if f.endswith(".json"):
                sk = TR.jload(os.path.join(self.root, f))
                if include_retired or sk["status"] == "active":
                    out.append(sk)
        return out

    # --- поиск (BM25)
    def search(self, query, k=3):
        docs = [(sk, toks(" ".join([sk["name"].replace("_", " "), sk["description"], " ".join(sk["tags"])]))) for sk in self.list()]
        q = toks(query)
        if not docs or not q:
            return []
        N = len(docs)
        avg = sum(len(d) for _, d in docs) / N or 1
        df = {}
        for _, d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        scored = []
        for sk, d in docs:
            s = 0.0
            for t in set(q):
                f = d.count(t)
                if f:
                    idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                    s += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * len(d) / avg))
            if s > 0:
                # надёжность: сглаженная доля успехов по Лапласу
                rel = (sk["runs"] - sk["fails"] + 1) / (sk["runs"] + 2)
                scored.append((s * (0.5 + rel), sk))
        scored.sort(key=lambda x: -x[0])
        return [{"name": sk["name"], "score": round(s, 3), "params": sk["params"], "description": sk["description"]} for s, sk in scored[:k]]

    # --- применение
    def instantiate(self, name, params, task_id):
        sk = self._load(name)
        if sk["status"] != "active":
            raise SkillError("skill %s is %s" % (name, sk["status"]))
        missing = set(sk["params"]) - set(params)
        extra = set(params) - set(sk["params"])
        if missing or extra:
            raise SkillError("params mismatch: missing %s extra %s" % (sorted(missing), sorted(extra)))
        card = _subst(sk["template"], params)
        card["id"] = task_id
        card["title"] = card.get("title") or sk["description"]
        card["skill"] = {"name": name, "sha": sk["sha"]}
        TR.validate_card(card)
        return card

    def record(self, name, ok):
        sk = self._load(name)
        sk["runs"] += 1
        sk["fails"] += 0 if ok else 1
        if sk["runs"] >= 4 and sk["fails"] / sk["runs"] > 0.5:
            sk["status"] = "retired"
        self._save(sk)
        return sk["status"]
