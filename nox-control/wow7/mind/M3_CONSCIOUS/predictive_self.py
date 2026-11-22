"""Предсказательное я NOX (M3_CONSCIOUS): прогноз -> ход -> ошибка предсказания -> внимание/модели/любопытство.

Функциональный механизм (predictive processing / active inference, Friston; AST-1, PP-1, AE-2 из Butlin/Long 2023),
НЕ заявление о переживании. Перед каждым ходом NOX фиксирует прогноз (реакция Создателя, исход задачи, своё
состояние); прогноз пишется в журнал с цепочкой хешей ДО ответа, поэтому задним числом его не подправить.
После хода считается ошибка по тем компонентам, что наблюдены; ошибка (нормированная на привычный уровень)
даёт «удивление» 0..1, которое:
  1) поднимает остроту сигнала в рабочем пространстве CON (ws.post, kind='discrepancy');
  2) ускоряет обучение таблиц «модель Создателя» и «модель себя» (темп обучения растёт с удивлением);
  3) питает любопытство: контексты с высоким и УБЫВАЮЩИМ удивлением (progress по Oudeyer) получают больший вес,
     а необучаемый шум (высокое удивление без прогресса) приглушается;
  4) отбирает эпизоды для ночного дообучения Soul-модели (export_training_rows).
Каждый прогноз сравнивается с базовым предсказателем (скользящие средние по таблицам, без LLM): навык
skill = 1 - err_модели / err_базы. Если LLM не лучше таблицы, это видно в report(), а не домысливается.

LLM подменяется: llm(messages, max_tokens, temperature) -> str (сигнатура nox_inner_loop). stdlib only.
"""
import hashlib
import json
import math
import os
import random
import re
import sys
import time

_here = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_here, "..", "..", "COMMON"), os.path.join(_here, "COMMON"), os.environ.get("NOX_COMMON", "")):
    if _p and os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)
try:
    import statefile as _sf
except ImportError:  # автономный запуск: минимальная замена с тем же контрактом
    _sf = None

LABELS = ("approve", "neutral", "correct", "frustrated", "silent")
LENGTHS = ("short", "medium", "long")
W_COMP = {"reaction": 0.5, "outcome": 0.3, "latency": 0.2}
MAX_HISTORY = 500
JSON_RE = re.compile(r"\{.*\}", re.S)


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _load(path, default):
    if _sf:
        return _sf.load(path, default)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save(path, obj):
    if _sf:
        return _sf.save(path, obj)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _append(path, line):
    if _sf:
        return _sf.append_line(path, line)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")
        f.flush()
        os.fsync(f.fileno())


def _dist(d, labels):
    return {k: float(d.get(k, 1.0 / len(labels))) for k in labels}


def _argmax(d):
    return max(d.items(), key=lambda kv: kv[1])[0]


def _new_creator():
    return {"n": 0, "valence": 0.0, "label": {k: 1.0 / len(LABELS) for k in LABELS},
            "length": {k: 1.0 / len(LENGTHS) for k in LENGTHS}, "followup": 0.5}


def _new_self():
    return {"n": 0, "succ": 0.7, "lat_log": math.log(10.0), "conf_bias": 0.0}


class PredictiveSelf:
    def __init__(self, state_path, llm=None, clock=time.time, pending_ttl=6 * 3600.0, rng_seed=7):
        self.path = state_path
        self.chain_path = state_path + ".chain.jsonl"
        self.llm = llm
        self.clock = clock
        self.pending_ttl = pending_ttl
        self.seed = rng_seed
        self.s = _load(state_path, None) or {
            "pending": {}, "creator": {}, "self": {}, "curiosity": {}, "history": [],
            "err_mean": 0.3, "chain_head": "0" * 64, "exported": [], "last": None}

    # ---------- хранение ----------
    def save(self):
        _save(self.path, self.s)

    def _chain(self, typ, turn_id, data):
        rec = {"type": typ, "turn_id": turn_id, "ts": self.clock(), "data": data, "prev": self.s["chain_head"]}
        rec["hash"] = _sha({k: rec[k] for k in ("type", "turn_id", "ts", "data", "prev")})
        _append(self.chain_path, json.dumps(rec, ensure_ascii=False))
        self.s["chain_head"] = rec["hash"]
        return rec["hash"]

    def verify_chain(self):
        """Проверка цепочки: (ok, n_записей, причина). Подмена или удаление прогноза ломает хеш."""
        prev, n = "0" * 64, 0
        try:
            with open(self.chain_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    r = json.loads(line)
                    base = {k: r[k] for k in ("type", "turn_id", "ts", "data", "prev")}
                    if r["prev"] != prev or r["hash"] != _sha(base):
                        return False, n, "разрыв на записи %d (turn %s)" % (n, r.get("turn_id"))
                    prev, n = r["hash"], n + 1
        except FileNotFoundError:
            return (prev == self.s["chain_head"]), 0, "журнала нет"
        if prev != self.s["chain_head"]:
            return False, n, "голова цепочки не совпала (журнал усечён)"
        return True, n, "ok"

    # ---------- базовый предсказатель (без LLM) ----------
    def baseline(self, ctx):
        c = self.s["creator"].get(ctx) or _new_creator()
        sf = self.s["self"].get(ctx) or _new_self()
        return {"creator": {"valence": round(c["valence"], 3), "label": _argmax(_dist(c["label"], LABELS)),
                            "length": _argmax(_dist(c["length"], LENGTHS)), "followup": c["followup"] >= 0.5},
                "outcome": {"success_p": round(_clamp(sf["succ"], 0.02, 0.98), 3)},
                "self": {"confidence": round(_clamp(sf["succ"], 0.02, 0.98), 3), "latency_s": round(math.exp(sf["lat_log"]), 2)}}

    def priors_lines(self, ctx):
        """Строки для промпта прогноза и для блока «Я сейчас»; только с данными (n>=3)."""
        out = []
        c = self.s["creator"].get(ctx)
        if c and c["n"] >= 3:
            out.append("Опыт (%d ходов этого типа): Создатель чаще всего '%s', длина ответа '%s', валентность %.2f." %
                       (c["n"], _argmax(_dist(c["label"], LABELS)), _argmax(_dist(c["length"], LENGTHS)), c["valence"]))
        sf = self.s["self"].get(ctx)
        if sf and sf["n"] >= 3:
            out.append("Мои исходы этого типа: успех %.0f%%, обычное время %.1f с, самоуверенность %+.2f." %
                       (sf["succ"] * 100, math.exp(sf["lat_log"]), sf["conf_bias"]))
        return out

    # ---------- прогноз ----------
    def _parse(self, raw, base):
        m = JSON_RE.search(raw or "")
        if not m:
            return None
        try:
            j = json.loads(m.group(0))
            cr, oc, sf = j["creator"], j["outcome"], j["self"]
            label = cr.get("label")
            length = cr.get("length")
            if label not in LABELS or length not in LENGTHS:
                return None
            return {"creator": {"valence": round(_clamp(float(cr["valence"]), -1, 1), 3), "label": label,
                                "length": length, "followup": bool(cr.get("followup", False))},
                    "outcome": {"success_p": round(_clamp(float(oc["success_p"]), 0.0, 1.0), 3)},
                    "self": {"confidence": round(_clamp(float(sf["confidence"]), 0.0, 1.0), 3),
                             "latency_s": round(_clamp(float(sf["latency_s"]), 0.05, 3600.0), 2)}}
        except (ValueError, KeyError, TypeError, AttributeError):
            return None

    def predict(self, turn_id, ctx, user_text, extra=""):
        """Зафиксировать прогноз ДО ответа. Возвращает {'pred','base','llm_ok','hash'}."""
        base = self.baseline(ctx)
        pred, llm_ok = None, False
        if self.llm:
            sys_p = ("Ты — предсказательный слой NOX. Прежде чем отвечать, оцени, что будет. Отвечай ТОЛЬКО JSON: "
                     '{"creator":{"valence":-1..1,"label":"approve|neutral|correct|frustrated|silent",'
                     '"length":"short|medium|long","followup":true|false},"outcome":{"success_p":0..1},'
                     '"self":{"confidence":0..1,"latency_s":число}}')
            user = "Тип хода: %s\n%s\nРеплика Создателя: %s\n%s" % (ctx, "\n".join(self.priors_lines(ctx)), user_text[:600], extra[:300])
            try:
                pred = self._parse(self.llm([{"role": "system", "content": sys_p}, {"role": "user", "content": user}], 160, 0.3), base)
            except Exception:
                pred = None
            llm_ok = pred is not None
        if pred is None:
            pred = json.loads(json.dumps(base))
        h = self._chain("pred", turn_id, {"ctx": ctx, "pred": pred, "base": base, "llm_ok": llm_ok})
        self.s["pending"][turn_id] = {"ts": self.clock(), "ctx": ctx, "pred": pred, "base": base, "llm_ok": llm_ok,
                                      "hash": h, "obs": {}, "user_text": user_text[:300]}
        self._gc()
        self.save()
        return {"pred": pred, "base": base, "llm_ok": llm_ok, "hash": h}

    def _gc(self):
        now = self.clock()
        for k in [k for k, p in self.s["pending"].items() if now - p["ts"] > self.pending_ttl]:
            del self.s["pending"][k]

    # ---------- наблюдение и ошибка ----------
    @staticmethod
    def errors(pred, obs):
        """Ошибки по наблюдённым компонентам -> {'reaction','outcome','latency','total'} (None, если не наблюдалось)."""
        e = {"reaction": None, "outcome": None, "latency": None}
        r = obs.get("reaction")
        if r:
            parts = []
            if "valence" in r:
                parts.append(abs(pred["creator"]["valence"] - _clamp(float(r["valence"]), -1, 1)) / 2.0)
            if "label" in r:
                parts.append(0.0 if pred["creator"]["label"] == r["label"] else 1.0)
            if "length" in r and r["length"] in LENGTHS:
                parts.append(abs(LENGTHS.index(pred["creator"]["length"]) - LENGTHS.index(r["length"])) / 2.0)
            if "followup" in r:
                parts.append(0.0 if pred["creator"]["followup"] == bool(r["followup"]) else 1.0)
            e["reaction"] = sum(parts) / len(parts) if parts else None
        if obs.get("outcome") is not None:
            e["outcome"] = (pred["outcome"]["success_p"] - (1.0 if obs["outcome"] else 0.0)) ** 2
        if obs.get("latency_s"):
            e["latency"] = min(1.0, abs(math.log(max(0.05, obs["latency_s"]) / pred["self"]["latency_s"])) / math.log(4.0))
        have = {k: v for k, v in e.items() if v is not None}
        wsum = sum(W_COMP[k] for k in have)
        e["total"] = (sum(W_COMP[k] * v for k, v in have.items()) / wsum) if wsum else None
        return e

    def observe(self, turn_id, reaction=None, outcome=None, latency_s=None, final=False):
        """Передать наблюдение (можно частями: исход и время сразу, реакция со следующей репликой).
        Закрывает ход, когда есть все три компонента или final=True. -> результат закрытия или {'status':'partial'}."""
        p = self.s["pending"].get(turn_id)
        if not p:
            return {"status": "unknown_turn"}
        if reaction is not None:
            p["obs"]["reaction"] = reaction
        if outcome is not None:
            p["obs"]["outcome"] = bool(outcome)
        if latency_s is not None:
            p["obs"]["latency_s"] = float(latency_s)
        have = {"reaction" in p["obs"], "outcome" in p["obs"], "latency_s" in p["obs"]}
        if not (final or have == {True}):
            self.save()
            return {"status": "partial", "have": sorted(p["obs"])}
        return self._close(turn_id)

    def _close(self, turn_id):
        p = self.s["pending"].pop(turn_id)
        ctx, obs = p["ctx"], p["obs"]
        em, eb = self.errors(p["pred"], obs), self.errors(p["base"], obs)
        if em["total"] is None:
            self.save()
            return {"status": "no_observation"}
        mean = max(0.05, self.s["err_mean"])
        surprise = round(em["total"] / (em["total"] + mean), 4)           # 0.5 при привычной ошибке, ->1 при сильной
        self.s["err_mean"] = 0.95 * self.s["err_mean"] + 0.05 * em["total"]
        self._learn(ctx, obs, p["pred"], surprise)
        self._curiosity(ctx, surprise)
        rec = {"turn_id": turn_id, "ts": self.clock(), "ctx": ctx, "surprise": surprise, "err_model": round(em["total"], 4),
               "err_base": round(eb["total"], 4), "llm_ok": p["llm_ok"], "components": {k: (round(v, 4) if v is not None else None) for k, v in em.items()},
               "brier": round(em["outcome"], 4) if em["outcome"] is not None else None}
        h = self._chain("obs", turn_id, {"obs": obs, "errors": rec["components"], "surprise": surprise, "pred_hash": p["hash"]})
        rec["hash"] = h
        self.s["history"].append(rec)
        del self.s["history"][:-MAX_HISTORY]
        self.s["last"] = {"turn_id": turn_id, "ctx": ctx, "surprise": surprise, "pred": p["pred"], "obs": obs, "user_text": p["user_text"]}
        self.s.setdefault("episodes", []).append({"turn_id": turn_id, "ctx": ctx, "user_text": p["user_text"], "pred": p["pred"],
                                                   "obs": obs, "surprise": surprise})
        del self.s["episodes"][:-MAX_HISTORY]
        self.save()
        return {"status": "closed", "surprise": surprise, "err_model": rec["err_model"], "err_base": rec["err_base"], "components": rec["components"]}

    # ---------- обучение моделей Создателя и себя ----------
    def _learn(self, ctx, obs, pred, surprise):
        c = self.s["creator"].setdefault(ctx, _new_creator())
        sf = self.s["self"].setdefault(ctx, _new_self())
        r = obs.get("reaction") or {}
        lr_c = min(0.6, max(1.0 / (c["n"] + 1), 0.1) * (0.5 + surprise))
        if r:
            c["n"] += 1
            if "valence" in r:
                c["valence"] += lr_c * (_clamp(float(r["valence"]), -1, 1) - c["valence"])
            if r.get("label") in LABELS:
                for k in LABELS:
                    c["label"][k] += lr_c * ((1.0 if k == r["label"] else 0.0) - c["label"][k])
            if r.get("length") in LENGTHS:
                for k in LENGTHS:
                    c["length"][k] += lr_c * ((1.0 if k == r["length"] else 0.0) - c["length"][k])
            if "followup" in r:
                c["followup"] += lr_c * ((1.0 if r["followup"] else 0.0) - c["followup"])
        lr_s = min(0.6, max(1.0 / (sf["n"] + 1), 0.1) * (0.5 + surprise))
        touched = False
        if obs.get("outcome") is not None:
            y = 1.0 if obs["outcome"] else 0.0
            sf["succ"] += lr_s * (y - sf["succ"])
            sf["conf_bias"] += lr_s * ((pred["self"]["confidence"] - y) - sf["conf_bias"])
            touched = True
        if obs.get("latency_s"):
            sf["lat_log"] += lr_s * (math.log(max(0.05, obs["latency_s"])) - sf["lat_log"])
            touched = True
        if touched:
            sf["n"] += 1

    # ---------- любопытство ----------
    def _curiosity(self, ctx, surprise):
        q = self.s["curiosity"].setdefault(ctx, {"slow": surprise, "fast": surprise, "n": 0})
        q["slow"] += 0.05 * (surprise - q["slow"])
        q["fast"] += 0.3 * (surprise - q["fast"])
        q["n"] += 1

    def curiosity_targets(self, k=3):
        """Контексты, где модель Создателя/себя ещё плохо предсказывает и это можно выучить. -> [(ctx, score, note)]."""
        out = []
        for ctx, q in self.s["curiosity"].items():
            progress = q["slow"] - q["fast"]                     # >0: удивление падает, значит обучение идёт
            score = q["slow"] * (1.0 / math.sqrt(q["n"] + 1) + 0.3) + 0.5 * max(0.0, progress)
            note = "изучать"
            if q["n"] >= 20 and q["slow"] > 0.6 and progress <= 0.01:
                score *= 0.4
                note = "похоже на шум: нужен новый признак, а не больше данных"
            elif q["n"] < 5:
                note = "мало данных"
            out.append((ctx, round(score, 4), note))
        return sorted(out, key=lambda x: -x[1])[:k]

    # ---------- связь с рабочим пространством CON ----------
    def post_to_workspace(self, ws, surprise_floor=0.55):
        """ws.post(key, text, salience, kind, ttl) — интерфейс CON/nox_workspace.Workspace (duck typing)."""
        n = 0
        last = self.s.get("last")
        if last and last["surprise"] >= surprise_floor:
            ws.post("pe:last", "Я ошибся в прогнозе (тип '%s', удивление %.0f%%): ждал '%s', вышло '%s'." % (
                last["ctx"], last["surprise"] * 100, last["pred"]["creator"]["label"],
                (last["obs"].get("reaction") or {}).get("label", "?")), last["surprise"], "discrepancy", ttl=1800)
            n += 1
        t = self.curiosity_targets(1)
        if t and t[0][1] >= 0.15 and "шум" not in t[0][2] and "мало данных" not in t[0][2]:
            ws.post("pe:curio", "Хочу лучше понять ходы типа '%s' (%s)." % (t[0][0], t[0][2]), min(1.0, t[0][1] * 1.5), "drive", ttl=3600)
            n += 1
        return n

    # ---------- ночное дообучение ----------
    def export_training_rows(self, out_path, min_surprise=0.65, limit=200):
        """Эпизоды с большим удивлением -> jsonl (instruction/output) для Soul-LoRA. Каждый эпизод выгружается один раз."""
        done = set(self.s["exported"])
        rows = [e for e in self.s.get("episodes", []) if e["surprise"] >= min_surprise and e["turn_id"] not in done]
        rows = sorted(rows, key=lambda e: -e["surprise"])[:limit]
        for e in rows:
            row = {"instruction": "Тип хода: %s\nРеплика Создателя: %s\nПредскажи реакцию Создателя и исход." % (e["ctx"], e["user_text"]),
                   "output": json.dumps(e["obs"], ensure_ascii=False), "surprise": e["surprise"], "turn_id": e["turn_id"]}
            _append(out_path, json.dumps(row, ensure_ascii=False))
            self.s["exported"].append(e["turn_id"])
        del self.s["exported"][:-2000]
        self.save()
        return len(rows)

    # ---------- честная проверка роста ----------
    def report(self, window=50, min_n=30, boot=400):
        """Растёт ли предсказательное я? Сравнение последнего окна с предыдущим + навык относительно таблицы-базы.
        Выводы только при n>=min_n в каждом окне; доверительный интервал — бутстрап (детерминированный seed)."""
        h = self.s["history"]
        cur, prev = h[-window:], h[-2 * window:-window]
        rep = {"n_total": len(h), "n_cur": len(cur), "n_prev": len(prev), "verdict": "мало данных", "claims_experience": False}
        if not cur:
            return rep

        def mean(xs):
            return sum(xs) / len(xs)

        def skill(rows):
            eb = mean([r["err_base"] for r in rows])
            return None if eb <= 1e-9 else 1.0 - mean([r["err_model"] for r in rows]) / eb
        rep["surprise_cur"] = round(mean([r["surprise"] for r in cur]), 3)
        rep["err_cur"] = round(mean([r["err_model"] for r in cur]), 4)
        rep["skill_vs_baseline_cur"] = None if skill(cur) is None else round(skill(cur), 3)
        br = [r["brier"] for r in cur if r["brier"] is not None]
        rep["brier_cur"] = round(mean(br), 3) if br else None
        if len(cur) >= min_n and len(prev) >= min_n:
            rng = random.Random(self.seed)
            diffs = []
            for _ in range(boot):
                a = [rng.choice(cur)["err_model"] for _ in cur]
                b = [rng.choice(prev)["err_model"] for _ in prev]
                diffs.append(mean(b) - mean(a))                    # >0: ошибка упала
            diffs.sort()
            lo, hi = diffs[int(0.05 * boot)], diffs[int(0.95 * boot) - 1]
            rep.update({"err_prev": round(mean([r["err_model"] for r in prev]), 4), "err_drop": round(mean([r["err_model"] for r in prev]) - mean([r["err_model"] for r in cur]), 4),
                        "err_drop_ci90": [round(lo, 4), round(hi, 4)]})
            rep["verdict"] = "ошибка падает (CI>0)" if lo > 0 else "ошибка растёт (CI<0)" if hi < 0 else "изменение не доказано"
        rep["note"] = "Измеряется точность прогноза себя и Создателя, а не переживание."
        return rep

    def render_lines(self):
        rep = self.report()
        if rep["n_total"] < 10:
            return ["Прогнозы: мало данных (%d закрытых ходов)." % rep["n_total"]]
        line = "Прогнозы (n=%d): средняя ошибка %.2f, навык против простой таблицы %s." % (
            rep["n_total"], rep["err_cur"], "н/д" if rep["skill_vs_baseline_cur"] is None else "%+.2f" % rep["skill_vs_baseline_cur"])
        return [line]
