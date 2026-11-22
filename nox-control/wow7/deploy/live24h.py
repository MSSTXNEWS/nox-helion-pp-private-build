#!/usr/bin/env python3
"""live24h.py: собирает /root/nox/receipts/LIVE-24H.json из квитанций приёмки (CONCEPT v7 §18, REVIEW_1 п.16). rc 0 = pass.
Критерии: chat_fast (ответ, ttft<=3 с) | chat_deep (GLM отвечает; если GLM не запущен - fail) | stop_receipt (PV-01 S7) | memory_source (S3) | fact_edit (S4) |
fresh_dialog_has_fix (S6) | wake (state/dsp_wake.json моложе 6 ч) | v7_stages (V7-00..V7-07: статус ok или rolled_back не допускается).
Ничего не выдумывает: нет файла = критерий failed с причиной."""
import argparse
import json
import os
import sys
import time

STEPS = {"stop_receipt": "S7", "memory_source": "S3", "fact_edit": "S4", "fresh_dialog_has_fix": "S6", "fast_route": "S1"}


def load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def last_json_line(p):
    try:
        for l in reversed(open(p, encoding="utf-8").read().strip().splitlines()):
            if l.startswith("{"):
                return json.loads(l)
    except (OSError, ValueError):
        pass
    return None


def build(rc, state, run, now=None):
    now = now or time.time()
    crit = {}
    fast = last_json_line(os.path.join(run, "live_fast.json"))
    crit["chat_fast"] = {"ok": bool(fast and fast.get("ok") and (fast.get("ttft_s") or 99) <= 3.0), "ttft_s": fast and fast.get("ttft_s"),
                         "why": None if fast else "нет live_fast.json"}
    deep = last_json_line(os.path.join(run, "live_deep.json"))
    crit["chat_deep"] = {"ok": bool(deep and deep.get("ok")), "ttft_s": deep and deep.get("ttft_s"), "why": None if deep else "GLM не отвечал/не запущен"}
    pv = load(os.path.join(rc, "ACT-PV01.json"))
    steps = {s["step"].split("_")[0]: s for s in (pv or {}).get("steps", [])}
    for k, sid in STEPS.items():
        st = steps.get(sid)
        crit[k] = {"ok": bool(st and st["ok"]), "why": None if st else ("нет ACT-PV01.json" if not pv else "шаг %s не выполнялся" % sid)}
    w = load(os.path.join(state, "dsp_wake.json"))
    crit["wake"] = {"ok": bool(w and now - float(w.get("ts", 0)) < 6 * 3600), "why": None if w else "нет state/dsp_wake.json (DSP wake не вызывался)"}
    stages = {}
    for i in range(0, 8):
        r = load(os.path.join(rc, "V7-%02d.json" % i))
        stages["V7-%02d" % i] = r.get("status") if r else "нет квитанции"
    bad = {k: v for k, v in stages.items() if v not in ("ok", "dry")}
    crit["v7_stages"] = {"ok": not bad, "stages": stages, "why": None if not bad else "не ok: %s" % bad}
    failed = [k for k, v in crit.items() if not v["ok"]]
    return {"id": "LIVE-24H", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "ok": not failed, "status": "pass" if not failed else "fail",
            "failed": failed, "first_broken_link": (pv or {}).get("first_broken_link"), "criteria": crit,
            "next": "SELF / WORLD-охота / SLP разрешены" if not failed else "чинить перечисленное, повторить S1_08"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receipts", required=True); ap.add_argument("--state", required=True); ap.add_argument("--run", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    r = build(a.receipts, a.state, a.run)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    print("LIVE-24H %s failed=%s" % (r["status"], r["failed"]))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
