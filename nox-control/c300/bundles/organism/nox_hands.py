#!/usr/bin/env python3
"""NOX руки (канон гл. 2, «Всегда живой»): исполнитель задач state/tasks (создаёт чат командой «/задача»; раньше их никто не брал: исполнителя не существовало, в supervisor «runners r01-r10» это GitHub-раннеры, не руки).
Цикл: queued -> dispatcher (nox_dispatch.decide_task: Go/NoGo + autonomy.authorize потока 4) -> running -> done | failed | needs_mind | awaiting_consent | refused | deferred(остаётся queued).
Безопасные типы без LLM/GPU: report, todo. Артефакт: state/tasks/artifacts/<id>.md из реальных данных. Квитанция (Action Receipt): state/receipts/<cid>_<id>_RECEIPT.json; done=true только при существующем артефакте с sha256.
Шина: task.started/progress/done/failed в state/bus/events.db. Доска state/core/board.json обновляется каждые 10 с. Для чата: can_claim_done(task_id) (можно ли говорить «сделал»), nox_board.answer(q).
Выключатели: state/hands.off, STOP-файлы. Команды: --once | --daemon."""
import os, sys, json, time, glob, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C, nox_bus as B, nox_board as BD, nox_dispatch as D
SRC = "hands"
def tdir(r): return r + "/state/tasks"
def rpath(r, t): return "%s/state/receipts/%s_%s_RECEIPT.json" % (r, t.get("cid"), t.get("id"))
def save_task(r, t, status, stage=None, **kw):
    t["status"] = status; t["updated_ts"] = time.time(); t.update(kw)
    if stage: t.setdefault("stages", []).append({"name": stage, "ts": t["updated_ts"]})
    C.atomic_json("%s/%s.json" % (tdir(r), t["id"]), t)
def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(65536), b""): h.update(b)
    return h.hexdigest()
def write_receipt(r, t, done, handler, artifact=None, dec=None, seqs=None, note=None):
    rc = C.load_json(rpath(r, t), {}) or {}
    rc.update({"task_id": t["id"], "cid": t.get("cid"), "status": t["status"], "done": bool(done), "handler": handler, "actor": "nox_hands", "ts": C.iso_msk(), "bus_seq": seqs or [], "auth": (dec or {}).get("auth"), "decision": {k: (dec or {}).get(k) for k in ("action", "go", "why", "value", "threshold")}})
    if note: rc["note"] = note
    if artifact and os.path.exists(artifact): rc["artifact"] = {"path": os.path.relpath(artifact, r), "sha256": sha_file(artifact), "bytes": os.path.getsize(artifact)}
    elif done: rc["done"] = False; rc["note"] = "артефакта нет: «сделал» не засчитано"
    os.makedirs(os.path.dirname(rpath(r, t)), exist_ok=True); C.atomic_json(rpath(r, t), rc); return rc
def can_claim_done(task_id, r=None):
    """Для chat_core: говорить «сделал» можно, только если квитанция done=true и артефакт на диске с тем же sha256."""
    r = r or C.root(); p = r + "/state/tasks/%s.json" % task_id; t = C.load_json(p, None)
    if not t or t.get("status") != "done": return False
    rc = C.load_json(rpath(r, t), {}) or {}; a = rc.get("artifact") or {}; ap = os.path.join(r, a.get("path", "")) if a.get("path") else None
    return bool(rc.get("done") and ap and os.path.exists(ap) and sha_file(ap) == a.get("sha256"))
# --------------------------------------------------------------- обработчики (чистый код, реальные данные)
def h_report(r, t):
    b = BD.build(r); s = b["slots"]; hd = s["hands"]; bd = s["body"]; m = s["mood"]
    L = ["# Отчёт о состоянии (%s)" % b["ts"], "", "Источник: self_now.json, шина событий, state/tasks. Числа реальные, чего нет — «нет данных».", "",
         "- Тело: VRAM %s%%, GPU %s°C, диск свободно %s ГБ, утомление F %s, CORT %s." % (bd["vram_pct"], bd["gpu_temp"], bd["disk_free_gb"], bd["F"], bd["CORT"]),
         "- Обучение: %s (идёт: %s)." % (bd["training"] or "нет данных", bd["train_running"]),
         "- Ощущение: %s (%s), причина в журнале: %s." % (m["top"], m["intensity"], m["cause"]), "- Голод: %s." % m["hunger"],
         "- Руки: в работе %d, в очереди %d, готово за сутки %d, ждут разума %d, ждут разрешения %d." % (len(hd["running"]), hd["queued"], hd["done_24h"], hd["hold_mind"], hd["awaiting_consent"]),
         "- Разговор: %s." % s["owner"]["last_talk"], "- Тревоги: %s." % (", ".join(s["alerts"]["items"]) or "нет")]
    return "\n".join(L) + "\n"
def h_todo(r, t):
    b = BD.build(r); s = b["slots"]; items = []
    for p in sorted(glob.glob(tdir(r) + "/*.json")):
        d = C.load_json(p, None)
        if isinstance(d, dict) and d.get("status") in ("queued", "running", "needs_mind", "awaiting_consent") and d.get("id") != t["id"]: items.append("задача %s: %s (%s)" % (d["id"], (d.get("title") or "")[:60], d["status"]))
    items = sorted(set(items))[:12]
    hq = C.load_json(C.S(r) + "/morning_queue.json", {}) or {}
    fp = [x for x in C.jl_tail(C.S(r) + "/forge_proposals.jsonl", 200) if x.get("status") == "proposed"]
    L = ["# Список дел (%s)" % b["ts"], "", "Собран из реальных источников: очередь задач, разрешения, предложения FORGE, тревоги тела.", ""]
    L += ["## Открытые задачи"] + (["- " + x for x in items] or ["- нет"]) + ["", "## Ждут разрешения Создателя", "- охота (разрешаешь?): %s" % hq.get("pending", 0), "- предложения FORGE без подписи: %d" % len({x["id"] for x in fp}), "", "## Тревоги тела"] + (["- " + x for x in s["alerts"]["items"]] or ["- нет"])
    return "\n".join(L) + "\n"
HANDLERS = {"report": h_report, "todo": h_todo}
# --------------------------------------------------------------- цикл
def ctx_of(r, now):
    sn = C.load_json(C.S(r) + "/self_now.json", {}) or {}; free = (sn.get("telemetry") or {}).get("disk_free_gb")
    busy = False
    try:
        if r != "/workspace/nox": raise RuntimeError("test root")
        sys.path.insert(0, "/workspace/nox/agent"); from nox_ops import common as OC; busy = bool(OC.chat_busy())
    except Exception: pass
    return {"disk_free": free if free is not None else 100.0, "chat_busy": busy, "now": now}
def process(r, t, ctx):
    tid = t["id"]; dec = D.decide_task(t, ctx, r); act = dec["action"]; seqs = []
    def ev(kind, extra=None): seqs.append(B.publish(kind, SRC, dict({"task": tid, "type": dec.get("type")}, **(extra or {})), trace_id=tid, r=r))
    if act == "defer": ev("task.deferred", {"why": dec["why"]}); return "deferred"
    if act == "halt": return "halt"
    if act == "hold_mind": save_task(r, t, "needs_mind", "ждёт разума", reason=dec["why"]); write_receipt(r, t, False, "none", dec=dec, seqs=seqs, note="не выполнено: нужен разум"); ev("task.progress", {"status": "needs_mind"}); return "needs_mind"
    if act == "refuse": save_task(r, t, "refused", "отказ по матрице автономии", reason=dec["why"]); write_receipt(r, t, False, "none", dec=dec, seqs=seqs, note="отказ"); ev("task.failed", {"why": dec["why"]}); return "refused"
    if act == "ask_consent": save_task(r, t, "awaiting_consent", "нужна карточка согласия", reason=dec["why"], card_text=dec.get("card_text")); write_receipt(r, t, False, "none", dec=dec, seqs=seqs, note="ждёт согласия"); ev("task.progress", {"status": "awaiting_consent"}); return "awaiting_consent"
    # run
    ev("task.started"); save_task(r, t, "running", "руки взяли в работу"); h = HANDLERS[dec["type"]]
    try:
        art_dir = tdir(r) + "/artifacts"; os.makedirs(art_dir, exist_ok=True); ap = "%s/%s.md" % (art_dir, tid)
        txt = h(r, t); open(ap + ".tmp", "w", encoding="utf-8").write(txt); os.replace(ap + ".tmp", ap); ev("task.progress", {"stage": "artifact", "bytes": len(txt)})
        save_task(r, t, "done", "готово: артефакт записан", artifact=os.path.relpath(ap, r)); rc = write_receipt(r, t, True, dec["type"], artifact=ap, dec=dec, seqs=seqs)
        if not rc["done"]: save_task(r, t, "failed", "артефакт не подтверждён"); ev("task.failed", {"why": "no_artifact"}); return "failed"
        ev("task.done", {"sha256": rc["artifact"]["sha256"][:12], "bytes": rc["artifact"]["bytes"]}); write_receipt(r, t, True, dec["type"], artifact=ap, dec=dec, seqs=seqs); return "done"
    except Exception as e:
        save_task(r, t, "failed", "ошибка рук", error=type(e).__name__); write_receipt(r, t, False, dec.get("type") or "none", dec=dec, seqs=seqs, note="ошибка " + type(e).__name__); ev("task.failed", {"error": type(e).__name__}); return "failed"
def tick(r=None, now=None, limit=5):
    r = r or C.root(); now = now if now is not None else time.time(); res = {"done": 0, "failed": 0, "needs_mind": 0, "refused": 0, "awaiting_consent": 0, "deferred": 0, "halt": 0}
    B.ensure(r)
    if os.path.exists(r + "/state/hands.off"): return dict(res, off=1)
    q = []
    for p in glob.glob(tdir(r) + "/*.json"):
        t = C.load_json(p, None)
        if isinstance(t, dict) and t.get("status") == "queued" and t.get("id"): q.append(t)
    q.sort(key=lambda t: float(t.get("created") or 0)); ctx = ctx_of(r, now)
    for t in q[:limit]:
        k = process(r, t, ctx); res[k] = res.get(k, 0) + 1
        if k in ("deferred", "halt"): break
    res["queued_left"] = len(q) - sum(res[k] for k in ("done", "failed", "needs_mind", "refused", "awaiting_consent"))
    return res
def daemon():
    r = C.root(); print("nox_hands start", C.iso_msk(), flush=True); n = 0; last_t = 0
    while True:
        t0 = time.time()
        try:
            BD.refresh(r)
            if t0 - last_t >= 20:
                last_t = t0; res = tick(r)
                if any(res.get(k) for k in ("done", "failed", "needs_mind", "refused", "awaiting_consent")) or n % 30 == 0: print("tick", json.dumps(res), flush=True)
            n += 1
        except Exception as e: print("tick_err", type(e).__name__, str(e)[:100], flush=True)
        time.sleep(max(1.0, 10 - (time.time() - t0)))
if __name__ == "__main__":
    if "--daemon" in sys.argv: daemon()
    else: print(json.dumps(tick(), ensure_ascii=False)); BD.refresh()
