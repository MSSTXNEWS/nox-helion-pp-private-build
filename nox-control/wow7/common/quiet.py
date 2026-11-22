"""quiet: ЕДИНЫЕ тихие часы NOX: [23:00, 08:00) МСК (REVIEW_1 п.4.4, исправление 7).

Диапазон из env NOX_QUIET ("23-8", "23:00-08:00", "22-7"); по умолчанию 23:00-08:00. Граница включающая слева, исключающая справа:
22:59 - не тихо, 23:00 - тихо, 07:59 - тихо, 08:00 - не тихо. МСК = UTC+3 без перехода на летнее время.
Python:  from quiet import in_quiet; in_quiet(ts)      Bash:  python3 quiet.py --check [--at <unix_ts>]  (код 0 = тихие часы)
"""
import os
import re
import sys
import time

MSK = 3 * 3600
DEFAULT = (23 * 60, 8 * 60)      # в минутах от полуночи


def _parse(s):
    m = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*[-–,]\s*(\d{1,2})(?::(\d{2}))?\s*", s or "")
    if not m:
        return None
    a = int(m.group(1)) * 60 + int(m.group(2) or 0)
    b = int(m.group(3)) * 60 + int(m.group(4) or 0)
    if not (0 <= a < 1440 and 0 <= b <= 1440) or a == b:
        return None
    return a, b % 1440


def window(spec=None):
    return _parse(spec if spec is not None else os.environ.get("NOX_QUIET", "")) or DEFAULT


def minute_msk(ts):
    return int(((ts + MSK) % 86400) // 60)


def in_quiet(ts=None, spec=None):
    """ts - unix-время (по умолчанию сейчас). spec - переопределение диапазона (для тестов)."""
    ts = time.time() if ts is None else ts
    a, b = window(spec)
    m = minute_msk(ts)
    return (m >= a or m < b) if a > b else (a <= m < b)


def hour_msk(ts):
    return ((ts + MSK) % 86400) / 3600.0


if __name__ == "__main__":
    at = float(sys.argv[sys.argv.index("--at") + 1]) if "--at" in sys.argv else None
    q = in_quiet(at)
    if "--check" in sys.argv:
        sys.exit(0 if q else 1)
    print("quiet" if q else "active")
