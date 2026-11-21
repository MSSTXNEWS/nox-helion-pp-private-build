"""core_block: компактный «блок ядра» для промпта: самое важное о личности, владельце и установках.

Отбор: тип записи (ядро > владелец > установки > подтверждённые факты), затем уверенность
по лестнице Riverse (уровень 0..3), закреплённость и важность; укладываемся в бюджет токенов.
Токены оцениваются грубо (1 токен ~ 3 символа русского текста): честная оценка без токенайзера.
"""
import math

CHARS_PER_TOKEN = 3.0
SECTIONS = [("core", "Ядро"), ("owner", "Владелец (обращение: мессир)"), ("settings", "Установки"), ("confirmed", "Подтверждённое")]
BASE = {"core": 100, "owner": 90, "settings": 80, "confirmed": 50}
FACT_SECTION = {"core": "core", "owner": "owner", "setting": "settings"}
PROFILE_SECTION = {"persona": "core", "owner": "owner", "settings": "settings"}
MAX_LINE = 300


def est_tokens(text):
    return int(math.ceil(len(text) / CHARS_PER_TOKEN)) if text else 0


def _clip(t, n=MAX_LINE):
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def render(groups):
    out = []
    for sec, title in SECTIONS:
        if groups.get(sec):
            out.append(title + ":")
            out.extend("- " + line for _, line, _ in groups[sec])
    return "\n".join(out)


def build_core_block(store, budget_tokens=400, min_level=0, extra_confirmed=True):
    """-> {"text", "items": [ref...], "tokens", "budget", "dropped": [ref...]}"""
    cands = []   # (score, section, ref, line)
    for p in store.profile():
        sec = PROFILE_SECTION.get(p["section"])
        if sec:
            cands.append((BASE[sec] + 5, sec, "p:" + p["key"], _clip("%s: %s" % (p["key"].split("/")[-1], p["value"]))))
    for f in store.active_facts():
        sec = FACT_SECTION.get(f["kind"])
        if sec is None:
            if not extra_confirmed or f["level"] < 2:
                continue
            sec = "confirmed"
        elif f["level"] < min_level and not f["pinned"]:
            continue
        score = BASE[sec] + f["level"] * 5 + (10 if f["pinned"] else 0) + f["importance"] * 5
        cands.append((score, sec, f["ref"], _clip(f["text"])))
    cands.sort(key=lambda c: (-c[0], c[2]))
    groups, used, dropped = {}, [], []
    for score, sec, ref, line in cands[:300]:
        trial = {k: list(v) for k, v in groups.items()}
        trial.setdefault(sec, []).append((score, line, ref))
        if est_tokens(render(trial)) <= budget_tokens:
            groups = trial
            used.append(ref)
        else:
            dropped.append(ref)
    text = render(groups)
    return {"text": text, "items": used, "tokens": est_tokens(text), "budget": budget_tokens, "dropped": dropped}
