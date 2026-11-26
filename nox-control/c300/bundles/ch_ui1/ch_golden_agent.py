# -*- coding: utf-8 -*-
"""ch-golden: раз в 24 ч перепроверяет модели советников golden-набором (6 фактовых вопросов, без CJK и без отката на локальную);
результат state/ch_verified.json читает pipeline_svc.verified(). Не стартует, пока чат занят; один прогон за раз."""
from __future__ import annotations
import os, subprocess, time
from . import lib as L

NAME = "ch-golden"
INTERVAL = 3600.0
VER = os.path.join(L.STATE, "ch_verified.json")
RUN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ch_golden_run.py")
OUT = os.path.join(L.STATE, "ch_golden_auto.out")
MAXAGE = 24 * 3600.0


def tick() -> dict:
    try:
        age = time.time() - os.path.getmtime(VER)
    except OSError:
        age = 1e9
    if age < MAXAGE:
        return {"action": "fresh", "age_h": round(age / 3600, 1)}
    if L.chat_busy():
        return {"action": "wait_chat_busy"}
    try:
        if subprocess.run(["pgrep", "-f", "ch_golden_run.py"], capture_output=True).stdout.strip():
            return {"action": "already_running"}
        subprocess.Popen(["python3", RUN], stdout=open(OUT, "w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        return {"action": "started", "age_h": round(age / 3600, 1)}
    except Exception as e:
        return {"action": "error", "error": "%s: %s" % (type(e).__name__, e)}
