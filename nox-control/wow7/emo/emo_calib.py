"""EMO-09: ночная самокалибровка базы настроения. Раз в сутки (в сон) сдвигает Mood.base к средней за 7 суток на <= 0.1 по оси.

Данные: mood_samples.jsonl (пишет Mood.update, шаг >= 10 мин). Порог минимума данных, а не отказ: при покрытии меньше MIN_DAYS суток
или MIN_SAMPLES точек запись «insufficient_data» в журнал без изменения базы; при покрытии 3..6 суток шаг масштабируется (step = 0.1 * дни/7);
при >= 7 суток - полный шаг. Страховка от дрейфа: суммарный уход от исходной базы <= MAX_DRIFT (0.3), откат rollback() к предыдущей/исходной.
Файлы: emo_base.json {"base","orig","history":[...]} (читает Mood), журнал emo_calib.jsonl. Только тихие часы (23-08 МСК), иначе пропуск (--force для проверки).
Запуск: python3 emo_calib.py [--state DIR] [--logs DIR] [--force] [--dry-run] | rollback
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

import statefile
from quiet import in_quiet

DEFAULT_BASE = (0.1, 0.0, 0.1)
MAX_STEP, MAX_DRIFT = 0.1, 0.3
WINDOW_DAYS, MIN_DAYS, MIN_SAMPLES = 7, 3, 24


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def read_samples(path, now, window_days=WINDOW_DAYS):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                    if now - window_days * 86400 <= r["ts"] <= now and len(r["vec"]) == 3:
                        out.append((float(r["ts"]), [float(x) for x in r["vec"]]))
                except (ValueError, KeyError, TypeError):
                    continue
    except OSError:
        pass
    return out


def compute(samples, base, orig, now=None):
    """-> dict: status, days, n, mean, new_base, step. Чистая функция (без файлов)."""
    n = len(samples)
    days = len({int((ts + 3 * 3600) // 86400) for ts, _ in samples})
    if n < MIN_SAMPLES or days < MIN_DAYS:
        return {"status": "insufficient_data", "n": n, "days": days, "need": {"samples": MIN_SAMPLES, "days": MIN_DAYS}}
    mean = [sum(v[i] for _, v in samples) / n for i in range(3)]
    k = min(1.0, days / float(WINDOW_DAYS))
    step = MAX_STEP * k
    new = []
    for b, m, o in zip(base, mean, orig):
        d = _clamp(m - b, -step, step)
        new.append(round(_clamp(b + d, o - MAX_DRIFT, o + MAX_DRIFT), 4))
    changed = any(abs(a - b) > 1e-9 for a, b in zip(new, base))
    return {"status": "calibrated" if changed else "unchanged", "n": n, "days": days, "mean": [round(x, 4) for x in mean],
            "step": round(step, 4), "base_before": list(base), "new_base": new}


def _load_base(path):
    d = statefile.load(path, None) or {}
    try:
        base = tuple(float(x) for x in d["base"])
        orig = tuple(float(x) for x in d["orig"])
        if len(base) == len(orig) == 3:
            return base, orig, list(d.get("history", []))
    except (KeyError, TypeError, ValueError):
        pass
    return DEFAULT_BASE, DEFAULT_BASE, []


def _log(logs_dir, rec):
    os.makedirs(logs_dir, exist_ok=True)
    statefile.append_line(os.path.join(logs_dir, "emo_calib.jsonl"), json.dumps(rec, ensure_ascii=False))


def calibrate(state_dir, logs_dir=None, now=None, force=False, dry_run=False):
    now = time.time() if now is None else now
    logs_dir = logs_dir or os.environ.get("NOX_LOGS", "/root/nox/logs")
    if not force and not in_quiet(now):
        return {"status": "skipped", "reason": "не тихие часы (калибровка - ночью)"}
    bp = os.path.join(state_dir, "emo_base.json")
    base, orig, hist = _load_base(bp)
    if hist and now - hist[-1]["ts"] < 20 * 3600 and not force:
        return {"status": "skipped", "reason": "уже калибровали в последние 20 ч"}
    res = compute(read_samples(os.path.join(state_dir, "mood_samples.jsonl"), now), base, orig)
    res["ts"] = now
    if res["status"] == "calibrated" and not dry_run:
        hist.append({"ts": now, "from": list(base), "to": res["new_base"]})
        statefile.save(bp, {"base": res["new_base"], "orig": list(orig), "history": hist[-30:]})
    if not dry_run:
        _log(logs_dir, res)
    return res


def rollback(state_dir, logs_dir=None, now=None):
    """Вернуть базу на шаг назад (или к исходной, если истории нет)."""
    now = time.time() if now is None else now
    bp = os.path.join(state_dir, "emo_base.json")
    base, orig, hist = _load_base(bp)
    if not hist:
        return {"status": "nothing_to_rollback"}
    last = hist.pop()
    statefile.save(bp, {"base": last["from"], "orig": list(orig), "history": hist})
    res = {"status": "rolled_back", "ts": now, "to": last["from"]}
    _log(logs_dir or os.environ.get("NOX_LOGS", "/root/nox/logs"), res)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "rollback"])
    ap.add_argument("--state", default=os.environ.get("NOX_STATE", "/root/nox/state"))
    ap.add_argument("--logs", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    r = rollback(a.state, a.logs) if a.cmd == "rollback" else calibrate(a.state, a.logs, force=a.force, dry_run=a.dry_run)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
