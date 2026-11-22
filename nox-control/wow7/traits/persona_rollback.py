"""persona_rollback: ОДНА команда отката личности - TRAITS + PER вместе (REVIEW_1 п.2, исправление 12).

Владелец состояния - TRAITS; PER (оси/темперамент) - агрегатор. Общий снапшот: snapshot_all(tr, per) кладёт один label в оба стора;
rollback_all(tr, per, label) сначала проверяет, что label есть в обоих (иначе ничего не меняется), затем откатывает ОБА; при сбое второго
первый возвращается из страховочного снапшота «pre-rollback-*». Событие откатывается в единый журнал жизни (kind=event).
CLI:  python3 persona_rollback.py snapshot|rollback [label]|list     (пути: NOX_TRAITS, NOX_PERSONALITY; подпись владельца проверяет вызывающий UI)
"""
import os as _os, sys as _sys
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json
import os
import sys
import time

import lifelink


def new_label(now=None):
    return "snap_" + time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time() if now is None else now))


def snapshot_all(tr, per, label=None, now=None):
    label = label or new_label(now)
    tr.snapshot(label, now=now)
    per.snapshot(label, now=now)
    return label


def common_labels(tr, per):
    return sorted(set(tr.snapshots) & set(per.snapshots), key=lambda k: max(tr.snapshots[k]["ts"], per.snapshots[k]["ts"]))


def rollback_all(tr, per, label=None, reason="откат личности (TRAITS+PER)"):
    if label is None:
        both = common_labels(tr, per)
        if not both:
            raise KeyError("нет общего снапшота TRAITS+PER")
        label = both[-1]
    if label not in tr.snapshots or label not in per.snapshots:
        raise KeyError("снапшот %r есть не в обоих сторах: TRAITS=%s PER=%s" % (label, label in tr.snapshots, label in per.snapshots))
    safety = "pre-rollback-%d" % int(time.time())
    snapshot_all(tr, per, safety)
    try:
        per.rollback(label, reason)
        tr.rollback(label, reason)
    except Exception:
        per.rollback(safety, "возврат после сбоя отката")
        tr.rollback(safety, "возврат после сбоя отката")
        raise
    lifelink.append("event", "%s: снапшот %s" % (reason, label), "per", state_dir=os.path.dirname(os.path.abspath(tr.path)),
                    data={"label": label, "safety": safety})
    return {"label": label, "safety": safety, "axes": dict(per.axes)}


def main(argv):
    import traits as T
    import personality as P
    tr, per = T.Traits(), P.Personality()
    cmd = argv[1] if len(argv) > 1 else "list"
    if cmd == "snapshot":
        print(snapshot_all(tr, per))
    elif cmd == "rollback":
        print(json.dumps(rollback_all(tr, per, argv[2] if len(argv) > 2 else None), ensure_ascii=False))
    else:
        print(json.dumps(common_labels(tr, per), ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv)
