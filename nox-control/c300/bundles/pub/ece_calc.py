#!/usr/bin/env python3
"""E7: расчёт ECE (канон гл.15 п.6) из state/mind/calibration.jsonl (пишет поток 3).
Строка JSON: уверенность (confidence|conf|p|prob, 0..1 или 0..100) + исход (correct|ok|is_correct|right|hit|label|y, bool/0/1).
ECE = sum_b (n_b/n) * |acc_b - conf_b| по 10 равным корзинам. Порог <= 0.1; n < MIN_N -> значение считается, но вердикт HOLD.
Запуск: python3 -I ece_calc.py [путь] -> печать JSON, запись state/mind/ece.json. Только stdlib."""
import os, sys, json, time
N = os.environ.get("NOX_ROOT", "/workspace/nox"); M = N + "/state/mind"
CK = ("confidence", "conf", "p", "prob", "probability"); OK = ("correct", "ok", "is_correct", "right", "hit", "label", "y")
MIN_N = int(os.environ.get("NOX_ECE_MIN_N", "50"))
def _pick(o, ks):
    for k in ks:
        if k in o and o[k] is not None: return o[k]
    return None
def load(path):
    pts = []; bad = 0
    try: lines = open(path, encoding="utf-8").read().splitlines()
    except Exception: return None, 0
    for l in lines:
        l = l.strip()
        if not l: continue
        try: o = json.loads(l)
        except Exception: bad += 1; continue
        c = _pick(o, CK); y = _pick(o, OK)
        if isinstance(c, bool) or not isinstance(c, (int, float)) or y is None: bad += 1; continue
        if isinstance(y, str): y = y.strip().lower() in ("1", "true", "yes", "да", "correct", "ok")
        c = float(c) / 100.0 if c > 1.0 else float(c)
        if not 0.0 <= c <= 1.0: bad += 1; continue
        pts.append((c, 1.0 if y else 0.0))
    return pts, bad
def ece(pts, bins=10):
    n = len(pts)
    if not n: return None, []
    bk = [[] for _ in range(bins)]
    for c, y in pts: bk[min(bins - 1, int(c * bins))].append((c, y))
    tot = 0.0; det = []
    for i, b in enumerate(bk):
        if not b: continue
        conf = sum(c for c, _ in b) / len(b); acc = sum(y for _, y in b) / len(b); tot += len(b) / n * abs(acc - conf)
        det.append({"bin": i, "n": len(b), "conf": round(conf, 3), "acc": round(acc, 3)})
    return round(tot, 4), det
def compute(path=None, write=True):
    path = path or M + "/calibration.jsonl"; pts, bad = load(path)
    if pts is None: r = {"ok": False, "reason": "нет файла calibration.jsonl", "n": 0}
    else:
        e, det = ece(pts); r = {"ok": e is not None, "ece": e, "n": len(pts), "bad_lines": bad, "min_n": MIN_N, "bins": det, "reason": None if len(pts) >= MIN_N else "мало данных: %d < %d" % (len(pts), MIN_N)}
    r["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if write:
        try: os.makedirs(M, exist_ok=True); open(M + "/ece.json", "w", encoding="utf-8").write(json.dumps(r, ensure_ascii=False))
        except Exception: pass
    return r
if __name__ == "__main__":
    print(json.dumps(compute(sys.argv[1] if len(sys.argv) > 1 else None), ensure_ascii=False))
