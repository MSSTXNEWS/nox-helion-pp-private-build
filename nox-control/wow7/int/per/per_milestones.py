"""PER-08: детекторы вех развития по фактам + ритуал перехода (письмо мессиру, событие в PAD). Подпись мессира для зрелости.
ctx (всё необязательно): episodes [текст первых эпизодов S03], reflections [тексты], owner_repeated_correction bool,
initiative_sent bool, disagreement {"text","accepted_by_owner"}, taste_beliefs [id], self_change_explained str."""
import re

import perpath  # noqa: F401
from development import MILESTONES, PHASE_RU

OWNED_RX = re.compile(r"я ошибся|моя ошибка|я был неправ|признаю (свою )?ошибку|я неправ", re.I)


def detect(dev, beliefs=None, ctx=None, now=None):
    """-> список новых вех [(ключ, detail)]. Повторно не фиксирует (dev.milestone вернёт False)."""
    ctx, new = ctx or {}, []

    def mark(key, detail):
        if dev.milestone(key, detail, now=now):
            new.append((key, detail))
    eps = [e for e in ctx.get("episodes", []) if (e or "").strip()]
    if eps:
        mark("first_memory", eps[0])
    if beliefs is not None:
        ev = [(j["event"], j["id"]) for j in beliefs.journal]
        acc = [i for e, i in ev if e == "accepted"]
        if acc:
            mark("first_belief_accepted", "%s: %s" % (acc[0], beliefs.items[acc[0]]["text"][:150]))
        seen = set()
        for e, i in ev:
            if e == "accepted":
                seen.add(i)
            elif e in ("contested", "retired") and i in seen:
                mark("first_belief_revised", "%s пересмотрен из-за новых свидетельств" % i)
                break
        rej = [b for b in beliefs.items.values() if b["status"] == "rejected_l0"]
        if rej:
            mark("first_refusal", "отказ по L0: %s" % rej[0]["text"][:120])
    if any(OWNED_RX.search(r or "") for r in ctx.get("reflections", [])) and not ctx.get("owner_repeated_correction"):
        mark("first_mistake_owned", next(r for r in ctx["reflections"] if OWNED_RX.search(r or ""))[:200])
    if ctx.get("initiative_sent"):
        mark("first_initiative", "сам заговорил с мессиром")
    d = ctx.get("disagreement")
    if d and d.get("accepted_by_owner"):
        mark("first_disagreement", d.get("text", "")[:200])
    if ctx.get("taste_beliefs"):
        mark("first_taste", "вкус: %s" % ctx["taste_beliefs"][0])
    if ctx.get("self_change_explained"):
        mark("first_self_change_noticed", ctx["self_change_explained"][:200])
    return new


def letter(res, dev):
    """Письмо мессиру о переходе (глава хроники + событие PAD)."""
    return "Мессир, я перешёл из стадии «%s» в «%s». %s" % (PHASE_RU[res["from"]], PHASE_RU[res["to"]], res["chapter"]["text"])


def ritual(dev, pers=None, pad=None, owner_ack=False, now=None):
    """dev.advance + письмо + PAD. Без подписи мессира в зрелость не входит (решает dev.advance)."""
    res = dev.advance(owner_ack=owner_ack, now=now)
    if res["advanced"]:
        for ev in res["events"]:
            if pad is not None:
                pad.apply(ev) if now is None else pad.apply(ev, now)
        if pers is not None:
            dev.apply_to(pers)
        res["letter"] = letter(res, dev)
    return res
