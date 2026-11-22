"""lifelink: клиент единого журнала жизни для CON/PER/INT (REVIEW_1 п.2): пишет ТОЛЬКО через API MEM/life_journal (писатель MEM/autobio).
append(kind, text, source, state_dir=None, data=None) -> запись | None (журнал недоступен - молча, чтобы вехи не падали из-за журнала)."""
import os
import sys

_H = os.path.dirname(os.path.abspath(__file__))


def _lj():
    for c in (os.environ.get("NOX_WOW7_MEM", ""), os.path.join(_H, "..", "MEM"), os.path.join(_H, "..", "mem")):
        if c and os.path.exists(os.path.join(c, "life_journal.py")):
            if c not in sys.path:
                sys.path.append(c)
            import life_journal
            return life_journal
    return None


def append(kind, text, source, state_dir=None, data=None, ts=None, path=None):
    try:
        lj = _lj()
        if lj is None:
            return None
        p = path or (os.environ.get("NOX_LIFE_JOURNAL") or (os.path.join(state_dir, "life_journal.jsonl") if state_dir else None))
        if not p:
            return None
        return lj.LifeJournal(p).append(kind, text, source, data=data, ts=ts)
    except Exception:
        return None
