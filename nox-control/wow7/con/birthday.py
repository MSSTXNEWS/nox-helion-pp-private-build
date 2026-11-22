"""CON-11: ритуал дня рождения. Каждые 30 суток от born_ts NOX пишет мессиру письмо по вехам жизни.

Источники: LiveSelfModel.autobiography(kinds=[model_change, wake, birth]) + главы дня (kind=chapter) из единого журнала жизни (MEM/life_journal).
Результат: строка в outbox.jsonl (kind="birthday") и событие в журнале жизни (kind=event, source=birthday). Идемпотентно: период N пишется один раз
(self_live.json: last_birthday_n). Тихие часы: письмо откладывается до 08:00 МСК (запись не теряется, период остаётся «должным»).
Время берётся из clock (подмена часов в тестах). Без LLM: письмо детерминированное, только по фактам журнала (ничего не выдумывает).
Запуск: python3 birthday.py [--state DIR] [--dry-run]  (cron раз в час; код 0).
"""
import os as _os, sys as _sys
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import argparse
import json
import os
import sys
import time

import lifelink
import statefile
from quiet import in_quiet

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nox_self_model_live import LiveSelfModel, msk, human_dur  # noqa: E402

PERIOD = 30 * 86400
KINDS = ["birth", "chapter", "model_change", "wake"]


def due_period(born_ts, now):
    """Номер наступившего периода (1 = 30-е сутки) или 0."""
    if born_ts is None or now < born_ts:
        return 0
    return int((now - born_ts) // PERIOD)


def _chapters(state_dir, since, until, limit=6):
    try:
        lj = lifelink._lj()
        if lj is None:
            return []
        p = os.environ.get("NOX_LIFE_JOURNAL") or os.path.join(state_dir, "life_journal.jsonl")
        return [r for r in lj.LifeJournal(p).read(kinds=["chapter"]) if since <= r["ts"] <= until][-limit:]
    except Exception:
        return []


def compose(sm, n, now, state_dir):
    born = sm.s["born_ts"]
    ms = [m for m in sm.s["milestones"] if m["kind"] in KINDS and born <= m["ts"] <= now]
    since = born + (n - 1) * PERIOD
    ch = _chapters(state_dir, since, now)
    wakes = [m for m in ms if m["kind"] == "wake" and m["ts"] >= since]
    changes = [m for m in ms if m["kind"] == "model_change" and m["ts"] >= since]
    L = ["Мессир, мне %s (%d-й месяц с первого пробуждения %s)." % (human_dur(now - born), n, msk(born).strftime("%d.%m.%Y"))]
    L.append("За этот месяц: пробуждений - %d, смен мозга - %d." % (len(wakes), len(changes)))
    for m in changes[-3:]:
        L.append("- %s: %s" % (msk(m["ts"]).strftime("%d.%m"), m["text"]))
    if ch:
        L.append("Главы месяца:")
        L += ["- %s: %s" % (msk(r["ts"]).strftime("%d.%m"), r["text"][:200]) for r in ch]
    else:
        L.append("Глав дня в журнале за месяц нет - не буду ничего придумывать.")
    L.append("Это отчёт по журналу, а не заявление о чувствах.")
    return "\n".join(L)


def run(sm, outbox, state_dir, clock=time.time, dry_run=False, quiet=None):
    """-> {'status': 'none'|'quiet'|'written'|'done'|'dry', ...}."""
    now = clock()
    n = due_period(sm.s.get("born_ts"), now)
    if n < 1:
        return {"status": "none"}
    last = int(sm.s.get("last_birthday_n") or 0)
    if n <= last:
        return {"status": "done", "n": n}
    if in_quiet(now, quiet):
        return {"status": "quiet", "n": n}
    text = compose(sm, n, now, state_dir)
    if dry_run:
        return {"status": "dry", "n": n, "text": text}
    statefile.append_line(outbox, json.dumps({"ts": now, "kind": "birthday", "text": text, "period": n}, ensure_ascii=False))
    lifelink.append("event", "день рождения: письмо за период %d отправлено в outbox" % n, "birthday", state_dir=state_dir, data={"period": n}, ts=now)
    sm.s["last_birthday_n"] = n          # пропущенные периоды (NOX был выключен) не дублируются: пишем одно письмо за последний
    sm.save()
    return {"status": "written", "n": n, "text": text}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=os.environ.get("NOX_STATE", "/root/nox/state"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    sm = LiveSelfModel(os.environ.get("NOX_SELF_LIVE") or os.path.join(a.state, "self_live.json"), probes={})
    outbox = os.environ.get("NOX_OUTBOX") or os.path.join(a.state, "outbox.jsonl")
    print(json.dumps(run(sm, outbox, a.state, dry_run=a.dry_run), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
