#!/usr/bin/env python3
"""Поток 6, волна 2: модель собеседника (TPJ, канон гл. 6) для Создателя и Димы. БЕЗ LLM, только stdlib.
Что считает: цели (темы, открытые обещания/просьбы), состояние (PAD с затуханием, усталость, срочность) и прогноз реакции на черновик ответа.
Откуда: события памяти пользователя (эпизоды/реплики/аффект-фид) + PAD. Ошибка прогноза -> «удивление» (канон: surprise), правила прогноза подстраиваются.
Память пользователей раздельная: модель создаётся на одного user (creator|dima), файл state/core/tpj_<user>.json; данные Создателя в модель Димы не попадают.
API: m = Model.load(user); m.update(ev); m.state(now); m.goals(); m.forecast(draft, now); m.observe(draft, reaction_text, now); m.block(now) -> строка в префикс; m.save()."""
import os, re, json, time, math, collections
N = os.environ.get("NOX_ROOT", "/workspace/nox"); ST = N + "/state/core"
HALF_LIFE_MIN = 120.0
POS = r"спасибо|отлично|класс|супер|здорово|круто|молодец|рад|нравится|получилось|работает|ура|прекрасно|хорошо"
NEG = r"плохо|ужас|бред|надоел|достал|опять|не работает|сломал|ошибк|раздража|бесит|тупи|медленно|зачем так|не то|неправильно|устал|тяжело|грустно|тревож"
URG = r"срочно|быстрее|сейчас же|немедленно|горит|дедлайн|скорее|пожалуйста,? быстро"
FATIGUE = r"устал|не выспал|сонн|вымотан|тяжёлый день|тяжелый день|нет сил|голова болит"
PROMISE = r"(?:напомни|не забудь|запомни|сделай (?:завтра|сегодня|вечером|к )|надо будет|нужно будет|проверь потом|вернись к)"
WANT = r"(?:хочу|хотел бы|мне нужно|мне нужна|нужно сделать|цель|план|собираюсь|давай (?:сделаем|начнём|начнем))"
STOPW = set("это как что для или так вот тут там они его нее ему если уже ещё еще только можно надо чтобы когда этот этой тоже очень просто потом сейчас нужно можешь давай есть будет было быть который которая".split())
def _w(t): return [x for x in re.findall(r"[а-яёa-z0-9]{4,}", str(t).lower()) if x not in STOPW]
def clamp(x, a=-1.0, b=1.0): return max(a, min(b, x))

def lexical_pad(text):
    """Грубая оценка PAD по тексту реплики (-1..1): v (приятность), a (возбуждение), d (контроль). Нужна, когда явного PAD нет."""
    t = str(text or "").lower(); n = max(1, len(_w(t)))
    pos = len(re.findall(POS, t)); neg = len(re.findall(NEG, t))
    ex = t.count("!"); caps = sum(1 for c in str(text) if c.isupper()) / max(1, len(str(text)))
    v = clamp((pos - neg) / max(1.0, math.sqrt(n)) * 0.6)
    a = clamp(0.15 * ex + 1.5 * caps + 0.4 * bool(re.search(URG, t)) + 0.2 * neg - 0.1)
    d = clamp(0.3 * bool(re.search(WANT, t)) - 0.3 * bool(re.search(FATIGUE + "|" + NEG, t)))
    return {"v": round(v, 3), "a": round(a, 3), "d": round(d, 3)}

def label(p):
    v, a = p["v"], p["a"]
    if v < -0.25 and a > 0.25: return "раздражение"
    if v < -0.25: return "грусть/усталость"
    if v > 0.25 and a > 0.25: return "радость"
    if v > 0.25: return "спокойное удовольствие"
    if a > 0.4: return "напряжение"
    return "нейтрально"

def draft_features(draft, user_text=""):
    """Признаки черновика ответа NOX (без LLM). Используются в прогнозе реакции."""
    d = str(draft or ""); words = len(d.split())
    try:
        import persona_guard as pg
        r = pg.guard(d, user=user_text); cl = int(r["cliche"]); sy = int(r["sycophantic"]); mo = int(r["monotony"])
    except Exception: cl = sy = mo = 0
    return {"long": int(words > 120), "very_long": int(words > 260), "short": int(words < 8), "question": int("?" in d), "cliche": cl, "flattery": sy, "monotony": mo,
            "list": int(len(re.findall(r"^\s*(?:[-*•]|\d+[.)])", d, re.M)) >= 3), "action_claim": int(bool(re.search(r"(?i)\bготово\b|\bсделал\b", d)))}

class Model:
    def __init__(self, user):
        self.user = user; self.events = []; self.w = {"base": 0.1, "long": -0.15, "very_long": -0.25, "short": -0.05, "question": 0.0, "cliche": -0.35, "flattery": -0.3,
            "monotony": -0.3, "list": -0.05, "action_claim": 0.05, "tired_long": -0.25, "urgent_long": -0.3, "urgent_short": 0.2}
        self.surprise = []; self.n_obs = 0; self.topics = collections.Counter(); self.open_items = []
    # ---- хранение
    @classmethod
    def load(cls, user, path=None):
        m = cls(user); p = path or "%s/tpj_%s.json" % (ST, user)
        try:
            d = json.load(open(p, encoding="utf-8")); m.w.update(d.get("w", {})); m.events = d.get("events", [])[-400:]; m.surprise = d.get("surprise", [])[-100:]; m.n_obs = d.get("n_obs", 0)
            m.topics = collections.Counter(d.get("topics", {})); m.open_items = d.get("open_items", [])
        except Exception: pass
        return m
    def save(self, path=None):
        p = path or "%s/tpj_%s.json" % (ST, self.user); os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"; json.dump({"user": self.user, "w": self.w, "events": self.events[-400:], "surprise": self.surprise[-100:], "n_obs": self.n_obs,
                                     "topics": dict(self.topics.most_common(60)), "open_items": self.open_items[-30:]}, open(tmp, "w", encoding="utf-8"), ensure_ascii=False); os.replace(tmp, p)
    # ---- события
    def update(self, ev):
        """ev: {ts, text, pad?{v,a,d}|v,a,d, kind?}; события только этого пользователя (чужие отбрасываются по ev['user'])."""
        if ev.get("user") not in (None, self.user): return False
        ts = float(ev.get("ts") or time.time()); text = str(ev.get("text") or "")
        pad = ev.get("pad") if isinstance(ev.get("pad"), dict) else ({k: ev[k] for k in ("v", "a", "d") if k in ev} or None)
        if not pad or "v" not in pad: pad = lexical_pad(text)
        pad = {"v": float(pad.get("v", 0)), "a": float(pad.get("a", 0)), "d": float(pad.get("d", 0))}
        e = {"ts": ts, "pad": pad, "len": len(text), "fatigue": int(bool(re.search(FATIGUE, text.lower()))), "urgent": int(bool(re.search(URG, text.lower())))}
        self.events.append(e); self.events = self.events[-400:]
        for w in _w(text): self.topics[w] += 1
        t = text.lower()
        if re.search(PROMISE, t) or re.search(WANT, t):
            self.open_items.append({"ts": ts, "kind": "promise" if re.search(PROMISE, t) else "want", "gist": " ".join(_w(text)[:6]), "done": False})
        if re.search(r"(?i)\b(?:готово|сделано|выполнено|закрыто|отмена|неважно|уже не надо)\b", t):
            for it in self.open_items[-5:]: it["done"] = True if re.search(r"|".join(re.escape(x) for x in _w(text)[:3] or ["_"]), it["gist"]) else it["done"]
        return True
    # ---- состояние
    def state(self, now=None):
        now = now or time.time(); num = [0.0, 0.0, 0.0]; den = 0.0
        for e in self.events[-80:]:
            age = max(0.0, (now - e["ts"]) / 60.0); w = 0.5 ** (age / HALF_LIFE_MIN)
            if w < 0.02: continue
            for i, k in enumerate("vad"): num[i] += w * e["pad"][k]
            den += w
        pad = {k: round(num[i] / den, 3) if den else 0.0 for i, k in enumerate("vad")}
        recent = [e for e in self.events if now - e["ts"] < 6 * 3600]
        fat = sum(e["fatigue"] for e in recent[-6:]) / 3.0
        hour = time.gmtime(now + 3 * 3600).tm_hour                   # МСК
        night = hour >= 23 or hour < 7
        urg = sum(e["urgent"] for e in recent[-3:]) / 2.0
        silence_h = round((now - self.events[-1]["ts"]) / 3600.0, 2) if self.events else None
        return {"pad": pad, "label": label(pad), "fatigue": round(min(1.0, fat + (0.3 if night else 0.0)), 2), "urgency": round(min(1.0, urg), 2), "night": night,
                "silence_h": silence_h, "conf": round(min(1.0, den / 3.0), 2), "n": len(self.events)}
    def goals(self, now=None, k=5):
        now = now or time.time()
        opn = [i for i in self.open_items if not i["done"] and now - i["ts"] < 7 * 86400]
        return {"topics": [w for w, _ in self.topics.most_common(k)], "open": [{"kind": i["kind"], "gist": i["gist"], "age_h": round((now - i["ts"]) / 3600.0, 1)} for i in opn[-k:]]}
    # ---- прогноз реакции: valence в [-1,1] (+ ожидаемая метка) и что учесть
    def forecast(self, draft, now=None, user_text=""):
        s = self.state(now); f = draft_features(draft, user_text); w = self.w
        sc = w["base"] + sum(w[k] * f[k] for k in f if k in w)
        if s["fatigue"] > 0.5 and f["long"]: sc += w["tired_long"]
        if s["urgency"] > 0.5: sc += w["urgent_long"] * f["long"] + w["urgent_short"] * f["short"]
        sc += 0.25 * s["pad"]["v"]
        val = round(clamp(sc), 3); lab = "доволен" if val > 0.2 else ("раздражение" if val < -0.2 else "нейтрально")
        adv = []
        if f["long"] and (s["fatigue"] > 0.5 or s["urgency"] > 0.5): adv.append("сократить: собеседник устал или торопится")
        if f["cliche"] or f["flattery"]: adv.append("убрать клише и лесть")
        if f["monotony"]: adv.append("сменить зачин и обращение")
        if s["pad"]["v"] < -0.25 and not f["question"]: adv.append("начать с признания состояния, одной фразой")
        return {"valence": val, "reaction": lab, "features": f, "advice": adv, "state": s["label"]}
    def observe(self, draft, reaction_text, now=None, user_text="", lr=0.15):
        """Что реально ответил человек на этот черновик -> ошибка прогноза (удивление) и поправка весов (дельта-правило)."""
        pred = self.forecast(draft, now, user_text)["valence"]; obs = clamp(lexical_pad(reaction_text)["v"] * 1.5)
        err = obs - pred; f = draft_features(draft, user_text)
        for k, x in f.items():
            if k in self.w and x: self.w[k] = round(self.w[k] + lr * err * x, 4)
        self.w["base"] = round(self.w["base"] + 0.05 * err, 4)
        self.n_obs += 1; self.surprise.append(round(abs(err), 3)); return {"pred": pred, "obs": round(obs, 3), "surprise": round(abs(err), 3), "surprising": abs(err) > 0.5}
    def block(self, now=None):
        """Короткая строка для префикса ответа (одна-две фразы), без текстов реплик."""
        s = self.state(now); g = self.goals(now, 3)
        parts = ["%s: %s" % (self.user, s["label"]) + (", усталость %.1f" % s["fatigue"] if s["fatigue"] >= 0.5 else "") + (", торопится" if s["urgency"] >= 0.5 else "") + (", ночь" if s["night"] else "")]
        if g["open"]: parts.append("открыто: " + "; ".join(i["gist"] for i in g["open"][-2:]))
        if g["topics"]: parts.append("темы: " + ", ".join(g["topics"]))
        return " | ".join(parts) + (" (уверенность %.1f)" % s["conf"])
    def mean_surprise(self, n=20):
        x = self.surprise[-n:]; return round(sum(x) / len(x), 3) if x else None

def from_feed(user, lines, now=None):
    """Построить модель из jsonl-строк аффект-фида/эпизодов; терпимо к форматам: ищет ts, text|content|user, pad|v,a,d."""
    m = Model(user)
    for l in lines:
        try: o = json.loads(l) if isinstance(l, str) else l
        except Exception: continue
        if not isinstance(o, dict): continue
        c = o.get("content") if isinstance(o.get("content"), dict) else {}
        text = o.get("text") or o.get("user") or c.get("user") or c.get("text") or (o.get("content") if isinstance(o.get("content"), str) else "")
        ts = o.get("ts") or o.get("t")
        if isinstance(ts, str):
            try: ts = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
            except Exception: ts = None
        o2 = {"ts": ts or time.time(), "text": text, "user": o.get("user_id") if o.get("user_id") in ("creator", "dima") else None}
        for k in ("pad", "v", "a", "d"):
            if k in o: o2[k] = o[k]
        m.update(o2)
    return m
