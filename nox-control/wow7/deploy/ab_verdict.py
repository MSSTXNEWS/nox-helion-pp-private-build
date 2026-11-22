#!/usr/bin/env python3
"""ab_verdict.py: решение «принять рычаг» по двум results.json ab_bench (опорный и кандидат) по правилам matrix.json (decision/quality).
Использование: ab_verdict.py --spd DIR_SPD --matrix M.json --ref R/results.json --cand C/results.json ; печатает JSON, rc 0 = принять."""
import argparse
import json
import os
import sys


def metrics(path):
    d = json.load(open(path, encoding="utf-8"))
    r = (d.get("results") or [{}])[0]
    return r.get("metrics")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--spd", required=True); ap.add_argument("--matrix", required=True); ap.add_argument("--ref", required=True); ap.add_argument("--cand", required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, a.spd)
    import ab_bench
    m = json.load(open(a.matrix, encoding="utf-8"))
    ref, cand = metrics(a.ref), metrics(a.cand)
    if not ref or not cand:
        print(json.dumps({"accepted": False, "reasons": ["нет метрик (база или кандидат не поднялись)"]}, ensure_ascii=False))
        return 1
    v = ab_bench.verdict(cand, ref, m["decision"], m["quality"])
    print(json.dumps(v, ensure_ascii=False))
    return 0 if v["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
