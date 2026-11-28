#!/usr/bin/env python3
"""NOX диспетчер «ситуация → действие» (канон гл. 2, аналог базальных ганглиев), чистый код. Go/NoGo = value >= threshold; опасное идёт через autonomy.authorize (поток 4, mods/autonomy.py).
Типы задач, которые «руки» умеют без LLM и без GPU: report (отчёт о состоянии), todo (список дел из реальных источников). Прочее -> hold_mind (ждёт разума, НЕ «сделано»).
decide_task(task, ctx) -> {"action": run|defer|ask_consent|refuse|hold_mind|halt, "go": bool, "type", "value", "threshold", "why", "auth"}"""
import os, sys, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C
try: import autonomy as AU
except Exception: AU = None
TYPES = [("report", re.compile(r"(статус|отч[её]т|состояни|как\s+(дела\s+у\s+)?тел|что\s+с\s+обучени|report|status)", re.I | re.U), "прочитай состояние системы и подготовь черновик отчёта"),
         ("todo", re.compile(r"(список\s+дел|дела\s+на|план\s+на|что\s+делать|чек-?лист|todo|to-do)", re.I | re.U), "прочитай состояние системы и подготовь черновик плана")]
HEAVY = ()  # типы, тяжёлые для CPU/GPU: откладываются, пока идёт ход чата. report/todo лёгкие (чтение файлов), чат не задерживают
def task_type(text):
    for n, rx, op in TYPES:
        if rx.search(text or ""): return n, op
    return None, None
def stop_active(r): return any(os.path.exists(p) for p in (r + "/STOP", "/run/nox/STOP", r + "/state/agents.off", r + "/state/hands.off"))
def authorize_task(text, op, origin, actor="creator"):
    """Строжайшая из категорий: текст задачи (если в нём есть опознанные правила) и операция рук."""
    if AU is None: return {"allowed": False, "level": "consent_card", "why": "no_autonomy_module", "cats": []}
    c = AU.classify(text)
    if c["known"] and c["level"] != "auto": return AU.authorize(text, actor=actor, origin=origin)
    return AU.authorize(op, actor=actor, origin=origin)
def decide_task(task, ctx, r=None):
    r = r or C.root(); text = task.get("text") or task.get("title") or ""; ty, op = task_type(text)
    origin = "user" if task.get("source") in ("chat", "owner", "ui") else "foreign"; actor = "creator" if task.get("user") == "owner" else "unknown"
    base = {"type": ty, "value": 0.0, "threshold": 0.2, "auth": None}
    if stop_active(r): return dict(base, action="halt", go=False, why="stop")
    if ty is None: return dict(base, action="hold_mind", go=False, why="нужен разум: тип задачи не из безопасных для рук")
    a = authorize_task(text, op, origin, actor); base["auth"] = {"level": a.get("level"), "allowed": a.get("allowed"), "why": a.get("why"), "cats": a.get("cats")}
    if a.get("level") in ("never", "creator_only") and not a.get("allowed"): return dict(base, action="refuse", go=False, why="autonomy:" + str(a.get("why")))
    if not a.get("allowed"): return dict(base, action="ask_consent", go=False, why="autonomy:" + str(a.get("why")), card_text=a.get("card_text"))
    if ctx.get("disk_free", 100) < 3.0: return dict(base, action="defer", go=False, why="диск < 3 ГБ: новая нагрузка не стартует")
    if ctx.get("chat_busy") and ty in HEAVY: return dict(base, action="defer", go=False, why="чат первый: идёт ход")
    age_h = (ctx.get("now", time.time()) - float(task.get("created") or 0)) / 3600.0
    val = 0.5 + (0.3 if task.get("user") == "owner" else 0.0) + min(0.2, 0.05 * age_h); base["value"] = round(val, 3)
    return dict(base, action="run", go=val >= base["threshold"], why="auto: " + str(a.get("why")))
