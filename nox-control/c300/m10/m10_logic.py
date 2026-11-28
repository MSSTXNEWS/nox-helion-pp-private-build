# -*- coding: utf-8 -*-
"""M10 pure logic (stdlib only): stems, triples, conflicts, time window, keep-score, kind/prov. No I/O."""
import re, math, time

STOP = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот от меня еще нет о из ему теперь когда даже ну ли если уже или ни быть был него до вас нибудь опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем чтобы нее сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через эти нас про всего них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя такой им более всегда конечно всю между пользователь пользователя пользователю пользователем пользователи говорил говорила сказал сказала помнишь помню какой какая какие каком каких""".split())

def norm(t): return t.lower().replace("ё", "е")
def stems(t, n=5):
    return [w[:n] for w in re.findall(r"[a-zа-я0-9]{3,}", norm(t)) if w not in STOP]

# ---------- provenance ----------
PROV_OK = ("thought", "heard", "web", "advisor")
def prov_norm(p, user="owner"):
    p = (p or "").strip().lower()
    if p in ("thought", "подумал"): return "thought", ""
    if p in ("web", "internet", "интернет"): return "web", ""
    if p in ("advisor", "советник"): return "advisor", ""
    if p.startswith("heard") or p.startswith("услышал"):
        x = p.split(":", 1)[1] if ":" in p else user
        return "heard", (x or user)[:40]
    return "heard", user[:40]
PROV_W = {"heard:owner": 1.0, "heard": 0.8, "thought": 0.5, "web": 0.5, "advisor": 0.6}
def prov_weight(prov, src):
    return PROV_W.get("heard:owner" if (prov == "heard" and src == "owner") else prov, 0.6)

# ---------- kind (protected: promise, value) ----------
_PROM = re.compile(r"обещ|пообещ|обязал|обязуюсь|договорил|не забудь|напомни|дал слово|клятв", re.I)
_VAL = re.compile(r"ценност|принцип|никогда не|всегда должен|главное для|важнее всего|запрет|нельзя", re.I)
def kind_of(text, source=""):
    s = (source or "")
    if "raw" in s or len(text) > 400: return "raw"
    if _PROM.search(text): return "promise"
    if _VAL.search(text): return "value"
    return "fact"
PROTECTED = ("promise", "value")

# ---------- triples / conflicts ----------
SINGLE = ("name", "age", "lives_in", "works")
_PET = r"(кошк|кот|кота|собак|пес|пёс|пса|попугай|хомяк|рыбк)"
def triples(text):
    t = norm(text); out = []
    m = re.search(_PET + r"\w*[^.;]{0,40}?(?:зовут|по имени|кличк\w*|имя)\s+([а-я\-]{2,})", t)
    pet = None
    if m:
        pet = m.group(2); out.append(("pet_name:" + m.group(1)[:3], m.group(2)[:5], m.group(2), 1))
    if not pet:
        m = re.search(r"(?:пользовател\w*\s+зовут|зовут|имя(?:\s+пользовател\w*)?\s*[-—:]?)\s+([а-я\-]{2,})", t)
        if m: out.append(("name", m.group(1)[:5], m.group(1), 1))
    m = re.search(r"(\d{1,3})\s*(?:лет|год|года)\b", t)
    if m and "пользовател" in t or (m and "мне" in t): out.append(("age", m.group(1), m.group(1), 1))
    m = re.search(r"(?:живет|проживает|переехал\w*|находится)\s+(?:в|на)\s+([а-я\-]+)", t)
    if m: out.append(("lives_in", m.group(1)[:5], m.group(1), 1))
    m = re.search(r"работает\s+(?:в|на|как)\s+([а-я\-]+)", t)
    if m: out.append(("works", m.group(1)[:5], m.group(1), 1))
    for m in re.finditer(r"(не\s+)?(?:любит|обожает|предпочитает)\s+([а-я\-]{3,})", t):
        out.append(("likes", m.group(2)[:4], m.group(2), -1 if m.group(1) else 1))
    return out

def conflicts(old_text, new_text):
    """-> list of (kind, pred, old_obj, new_obj). Empty = no contradiction."""
    res = []
    a, b = triples(old_text), triples(new_text)
    for p1, k1, o1, s1 in a:
        for p2, k2, o2, s2 in b:
            if p1 != p2: continue
            if p1 in SINGLE or p1.startswith("pet_name:"):
                if k1 != k2: res.append(("slot", p1, o1, o2))
            elif p1 == "likes" and k1 == k2 and s1 != s2:
                res.append(("polarity", p1, o1, o2))
    return res

def question(old_text, new_text, old_ts, new_ts, user):
    d = lambda ts: time.strftime("%d.%m.%Y", time.localtime(ts)) if ts else "?"
    who = "" if user == "owner" else " (собеседник: %s)" % user
    return "Противоречие в памяти%s. Раньше (%s) я записал: «%s». Теперь (%s): «%s». Что верно: новое, старое или оба?" % (who, d(old_ts), old_text[:160], d(new_ts), new_text[:160])

# ---------- time window ----------
_NUM = {"один": 1, "одну": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "двадцать": 20, "тридцать": 30}
def time_window(q, now=None):
    now = now or time.time(); t = norm(q); D = 86400.0
    if re.search(r"позавчера", t): return (now - 2 * D - 0.6 * D, now - 2 * D + 0.6 * D)
    if re.search(r"\bвчера", t): return (now - 1 * D - 0.6 * D, now - 1 * D + 0.6 * D)
    m = re.search(r"(\d+|%s)?\s*(дн\w+|день|недел\w+|месяц\w*)\s+назад" % "|".join(_NUM), t)
    if m:
        n = m.group(1); n = int(n) if (n and n.isdigit()) else _NUM.get(n or "", 1)
        u = m.group(2); days = n * (7 if u.startswith("недел") else 30 if u.startswith("месяц") else 1)
        hw = max(1.0, 0.3 * days)
        return (now - (days + hw) * D, now - max(0.0, days - hw) * D)
    if re.search(r"(на )?прошл\w+ недел", t): return (now - 14 * D, now - 5 * D)
    if re.search(r"(в )?прошл\w+ месяц", t): return (now - 62 * D, now - 20 * D)
    return None

# ---------- forgetting ----------
def keep_score(weight, repeats, uses, goal, age_days, half=30.0):
    rep = 1.0 + math.log(1.0 + max(0, repeats or 0) + max(0, uses or 0))
    rec = 0.5 ** (max(0.0, age_days) / half)
    return max(0.0, weight or 0.5) * rep * max(0.0, min(1.0, goal)) * rec
