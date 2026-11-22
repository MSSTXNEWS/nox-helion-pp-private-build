"""Пути к ядру PER/EMO: на сервере NOX_WOW7 (/root/nox/src/wow7), локально /home/claude/nox_wow."""
import os
import sys

ROOT = os.environ.get("NOX_WOW7") or os.environ.get("NOX_WOW_SRC") or "/home/claude/nox_wow"
for _p in (os.path.dirname(os.path.abspath(__file__)),):
    if _p not in sys.path:
        sys.path.append(_p)
for _d in ("PER", "EMO", "CON", "TRAITS"):
    _p = os.path.join(ROOT, _d)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)
