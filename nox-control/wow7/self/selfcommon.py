"""selfcommon: атомарная запись JSON, журнал JSONL, зажим чисел. Общее для voice_designer/ui_mutator/tastes (stdlib)."""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json

import statefile
import os
import time


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def write_json(path, obj):
    statefile.save(path, obj, indent=1)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def journal_add(path, rec):
    rec = dict(rec)
    rec.setdefault("ts", time.time())
    statefile.append_line(path, json.dumps(rec, ensure_ascii=False))
    return rec


def journal_read(path, last=None):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out[-last:] if last else out
