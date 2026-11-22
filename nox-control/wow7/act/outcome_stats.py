#!/usr/bin/env python3
"""outcome_stats: ожидаемая успешность вида действия по НЕЗАВИСИМО ПРОВЕРЕННЫМ исходам (идея из единого NOX Brain, NB1000).

p = (успехи + 1) / (успехи + неудачи + 2)  — Beta(1,1)-априор; число, а не самоуверенность модели.
Правила: исход пишется только с доказательством (evidence) и булевым success; событие идемпотентно по event_id (повтор не удваивает);
хранение — COMMON/statefile (межпроцессная блокировка, переживает перезапуск). Питает сигнал Генома work.pred_success
(правило nb.low_pred_caution): мало подтверждённых успехов -> превью, меньший шаг, проверка после.
API: record(kind, success, evidence, event_id, path=None) -> bool(принято) ; predict(kind, path=None) -> dict ; signal(kind, path=None) -> {"work.pred_success": p}
CLI: python3 outcome_stats.py predict <kind> | record <kind> <ok|fail> <evidence> <event_id>"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
for _c in (os.environ.get("NOX_COMMON", ""), os.path.join(HERE, "..", "COMMON"), os.path.join(HERE, "common")):
    if _c and os.path.isdir(_c) and _c not in sys.path:
        sys.path.append(_c)
import statefile

DEFAULT = os.environ.get("NOX_OUTCOMES", "/root/nox/state/outcomes.json")
MAX_EVENTS = 5000  # хвост id для идемпотентности; старее — забываем (счётчики остаются)


def _path(p):
    return p or DEFAULT


def record(kind, success, evidence, event_id, path=None):
    if not isinstance(kind, str) or not kind.strip() or len(kind) > 120:
        raise ValueError("kind required")
    if type(success) is not bool:
        raise ValueError("success must be bool (проверенный исход, не оценка модели)")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("independent evidence required")
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id required")
    took = []

    def upd(d):
        d = d or {}
        seen = d.setdefault("seen", [])
        if event_id in seen:
            return d
        k = d.setdefault("kinds", {}).setdefault(kind, {"success": 0, "failure": 0})
        k["success" if success else "failure"] += 1
        seen.append(event_id)
        del seen[:-MAX_EVENTS]
        took.append(1)
        return d
    statefile.update(_path(path), upd, default={})
    return bool(took)


def predict(kind, path=None):
    d = statefile.load(_path(path), default={}) or {}
    k = (d.get("kinds") or {}).get(kind, {"success": 0, "failure": 0})
    n = k["success"] + k["failure"]
    return {"kind": kind, "success_probability": (k["success"] + 1) / (n + 2), "observations": n,
            "basis": "verified_outcomes_beta_prior"}


def signal(kind, path=None):
    return {"work.pred_success": round(predict(kind, path)["success_probability"], 4)}


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    import json
    if len(a) == 2 and a[0] == "predict":
        print(json.dumps(predict(a[1]), ensure_ascii=False)); return 0
    if len(a) == 5 and a[0] == "record" and a[2] in ("ok", "fail"):
        print(json.dumps({"accepted": record(a[1], a[2] == "ok", a[3], a[4])})); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main())
