"""PER-04: ночная консолидация личности + развития + взглядов («сон»). Тихие часы 23:00-08:00 МСК.
CLI: python3 per_night.py [--force] [--state DIR]  -> JSON в stdout и строка в NOX_PER_NIGHT_LOG (/root/nox/logs/per_night.log).
Шаги: snapshot pre-night -> consolidate (потолок 0,02/сутки/ось) -> темперамент в PAD -> веха first_night -> внешние метрики развития ->
dev.check; если какая-то ось сдвинулась больше потолка - rollback("pre-night")."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json

import statefile
import os
import sys
import time

import perpath  # noqa: F401
from beliefs import Beliefs
from development import Development
from personality import AXES, DRIFT_CAP, Personality

MSK = 3 * 3600


from quiet import in_quiet           # единые тихие часы: COMMON/quiet.py


def run(pers, dev, beliefs, pad=None, log_path=None, now=None, force=False):
    now = pers.clock() if now is None else now
    if not force and not in_quiet(now):
        return {"skipped": "не тихие часы (23-08 МСК)"}
    dev.apply_to(pers)
    before = dict(pers.axes)
    pers.snapshot("pre-night", now=now)
    changes = pers.consolidate(now)
    cap = DRIFT_CAP * pers.scale + 1e-9
    over = {a: round(pers.axes[a] - before[a], 4) for a in AXES if abs(pers.axes[a] - before[a]) > cap}
    rolled = False
    if over:
        pers.rollback("pre-night", "ночной сдвиг выше потолка: %s" % over)
        rolled = True
    elif pad is not None:
        pers.apply_to(pad)
    dev.milestone("first_night", "ночная консолидация %s" % time.strftime("%Y-%m-%d", time.gmtime(now + MSK)), now=now)
    accepted = sum(1 for b in beliefs.items.values() if b["status"] == "accepted")
    rb_ts = {j["ts"] for j in pers.journal if j["kind"] == "rollback" and now - j["ts"] < 14 * 86400}
    dev.set_external(beliefs_accepted=accepted, rollbacks_14d=len(rb_ts))
    beliefs.min_sources = dev.params()["quarantine_sources"]
    beliefs.save()
    rep = {"ts": now, "changes": [list(c) if not isinstance(c, dict) else c for c in changes], "rolled_back": rolled, "over_cap": over,
           "signature": pers.signature()[1], "development": dev.check(now), "beliefs_accepted": accepted}
    path = log_path or os.environ.get("NOX_PER_NIGHT_LOG", "/root/nox/logs/per_night.log")
    try:
        statefile.append_line(path, json.dumps(rep, ensure_ascii=False))
    except OSError as e:
        rep["log_error"] = str(e)
    return rep


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    state = a[a.index("--state") + 1] if "--state" in a else os.environ.get("NOX_STATE", "/root/nox/state")
    j = lambda n: os.path.join(state, n)
    pers, dev, bel = Personality(path=j("personality.json")), Development(path=j("development.json")), Beliefs(path=j("beliefs.json"))
    rep = run(pers, dev, bel, force="--force" in a)
    print(json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
