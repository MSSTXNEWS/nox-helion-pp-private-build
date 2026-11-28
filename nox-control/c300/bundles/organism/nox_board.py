#!/usr/bin/env python3
"""NOX доска (рабочая память <=7 слотов, канон гл. 2): state/core/board.json. Слоты: goal, focus, hands, mood, body, owner, alerts. Собирается из self_now.json, шины (events.db board/events) и state/tasks.
Для потока 3 (chat_core): board.answer(question) -> {"text", "slots", "age_s", "ms"} за <=1 с (только чтение board.json/tasks, без сети и LLM); board.status_line(). Значения только реальные; чего нет: «нет данных»."""
import os, sys, re, json, time, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C, nox_bus as B
SLOTS = ("goal", "focus", "hands", "mood", "body", "owner", "alerts")
def tasks_view(r, now):
    out = {"running": [], "queued": 0, "done_24h": 0, "failed_24h": 0, "hold_mind": 0, "awaiting_consent": 0, "refused": 0, "total": 0}
    for p in glob.glob(r + "/state/tasks/*.json"):
        d = C.load_json(p, None)
        if not isinstance(d, dict): continue
        out["total"] += 1; st = d.get("status"); recent = now - float(d.get("updated_ts") or 0) < 86400
        if st == "running": out["running"].append({"id": d.get("id"), "title": (d.get("title") or "")[:60]})
        elif st == "queued": out["queued"] += 1
        elif st in ("done",) and recent: out["done_24h"] += 1
        elif st == "failed" and recent: out["failed_24h"] += 1
        elif st == "needs_mind": out["hold_mind"] += 1
        elif st == "awaiting_consent": out["awaiting_consent"] += 1
        elif st == "refused": out["refused"] += 1
    return out
def build(r=None, now=None):
    r = r or C.root(); now = now if now is not None else time.time()
    sn = C.load_json(C.S(r) + "/self_now.json", {}) or {}; tel = sn.get("telemetry") or {}; tf = sn.get("top_feeling"); pad = sn.get("pad") or {}; fat = sn.get("fatigue") or {}; pn = sn.get("panel") or {}
    g = B.board_get("goal", r) or {}; at = B.board_get("attention", r) or {}; tr = B.board_get("training", r) or {}
    tv = tasks_view(r, now)
    alerts = []
    if tel.get("disk_free_gb") is not None and tel["disk_free_gb"] < 15: alerts.append("диск %.1f ГБ (<15)" % tel["disk_free_gb"])
    if tel.get("vram_pct") is not None and tel["vram_pct"] > 92: alerts.append("VRAM %.0f%% (>92)" % tel["vram_pct"])
    hb = C.load_json(r + "/state/ops/heartbeat.json", {}) or {}
    bad = [k for k, v in (hb.get("services") or {}).items() if v.get("status") in ("ERROR",)]
    if bad: alerts.append("службы с ошибкой: " + ",".join(bad[:4]))
    if tv["hold_mind"]: alerts.append("задач ждут разума: %d" % tv["hold_mind"])
    s = {"goal": {"text": (g.get("text") or "цель дня не задана")[:160], "src": "bus.board.goal" if g else "нет данных"},
         "focus": {"text": str(at.get("text") or "нет данных")[:160], "src": "bus.board.attention"},
         "hands": dict(tv, src="state/tasks"),
         "mood": {"top": (tf or {}).get("name"), "intensity": (tf or {}).get("intensity"), "cause": (tf or {}).get("cause"), "pad": [pad.get("v"), pad.get("a"), pad.get("d")], "hunger": (sn.get("hunger") or {}).get("level"), "src": "self_now"},
         "body": {"vram_pct": tel.get("vram_pct"), "gpu_temp": tel.get("gpu_temp"), "disk_free_gb": tel.get("disk_free_gb"), "F": fat.get("F"), "CORT": pn.get("CORT"), "train_running": tel.get("train_running"), "training": (tr.get("text") or "")[:100], "src": "self_now+bus"},
         "owner": {"last_talk": (sn.get("last_talk") or {}).get("text"), "hunt_pending": (sn.get("hunt_queue") or {}).get("pending", 0), "src": "self_now"},
         "alerts": {"items": alerts[:5], "src": "derived"}}
    return {"ts": C.iso_msk(now), "t": now, "n_slots": len(s), "slots": s}
def refresh(r=None, now=None):
    b = build(r, now); C.atomic_json(C.S(r) + "/board.json", b); return b
def _fmt(x): return "нет данных" if x is None else x
def answer(question, r=None, now=None):
    """Ответ на «как там X?» из доски за <=1 с. Только чтение. -> dict(text, slots, age_s, ms, ok)."""
    t0 = time.time(); r = r or C.root(); now = now if now is not None else time.time(); q = (question or "").lower()
    b = C.load_json(C.S(r) + "/board.json", None)
    if not b or now - b.get("t", 0) > 300: b = build(r, now)
    s = b["slots"]; used = []; parts = []
    def has(*w): return any(x in q for x in w)
    if has("обучен", "тренир", "dpo", "рост", "адаптер"):
        used.append("body"); bd = s["body"]; parts.append("Обучение: %s; тело: VRAM %s%%, GPU %s°C, утомление %s." % (bd["training"] or ("идёт" if bd.get("train_running") else "не идёт"), _fmt(bd["vram_pct"]), _fmt(bd["gpu_temp"]), _fmt(bd["F"])))
    if has("тел", "gpu", "видеопам", "диск", "жар", "температур", "железо"):
        used.append("body"); bd = s["body"]; parts.append("Тело: VRAM %s%%, GPU %s°C, диск свободно %s ГБ." % (_fmt(bd["vram_pct"]), _fmt(bd["gpu_temp"]), _fmt(bd["disk_free_gb"])))
    if has("настроени", "чувств", "эмоц", "как ты"):
        used.append("mood"); m = s["mood"]; parts.append(("Сейчас ощущаю: %s (%.2f), причина в журнале %s." % (m["top"], m["intensity"] or 0, m["cause"])) if m.get("top") else "Сигнала для чувства сейчас нет.")
    if has("цел"): used.append("goal"); parts.append("Цель: %s." % s["goal"]["text"])
    if has("фокус", "внимани"): used.append("focus"); parts.append("Фокус: %s." % s["focus"]["text"])
    if has("разговор", "общени", "созда"): used.append("owner"); parts.append("%s." % _fmt(s["owner"]["last_talk"]))
    words = [w for w in re.split(r"\W+", q) if len(w) > 3]; hit = []
    if has("задач", "руки", "рук", "сделал", "дела", "очеред") or not parts:
        for p in glob.glob(r + "/state/tasks/*.json")[:2000]:
            d = C.load_json(p, None)
            if isinstance(d, dict) and any(w in (d.get("title") or "").lower() for w in words if w not in ("задача", "задачи", "как", "там", "дела")): hit.append(d)
        hit.sort(key=lambda d: -float(d.get("updated_ts") or 0)); used.append("hands"); h = s["hands"]
        if hit:
            d = hit[0]; rc = C.load_json("%s/state/receipts/%s_%s_RECEIPT.json" % (r, d.get("cid"), d.get("id")), {}) or {}
            parts.append("Задача %s: статус %s%s." % (d.get("id"), d.get("status"), ", артефакт есть, квитанция подтверждена" if rc.get("done") and (rc.get("artifact") or {}).get("sha256") else (", артефакта нет" if d.get("status") != "queued" else "")))
        else: parts.append("Руки: в работе %d, в очереди %d, готово за сутки %d, сорвано %d, ждут разума %d, ждут разрешения %d." % (len(h["running"]), h["queued"], h["done_24h"], h["failed_24h"], h["hold_mind"], h["awaiting_consent"]))
    return {"text": " ".join(parts), "slots": sorted(set(used)), "age_s": round(now - b.get("t", now), 1), "ms": round((time.time() - t0) * 1000, 1), "ok": True}
if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--ask": print(json.dumps(answer(" ".join(a[1:])), ensure_ascii=False))
    else: b = refresh(); print("board slots", b["n_slots"], list(b["slots"]))
