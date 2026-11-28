#!/usr/bin/env python3
"""NOX поглощение с SHA: реестр статусов, цепочка SHA в Genesis Ledger, откат (канон v6.1 гл. 9, 22). ТОЛЬКО ЗАПИСЬ СОБЫТИЙ: поглотитель, загрузка, дистилляция и удаление файлов здесь не запускаются.
Статусы: PROPOSED -> FETCHED -> VERIFIED -> ACTIVE_ADAPTER -> TRAINING -> ABSORBED -> REMOVED (строго по порядку); откат: ROLLED_BACK (запись-указатель на sha до).
Правила: FETCHED только после согласия Создателя (consent=approved); NC/неясная лицензия без решения Создателя дальше FETCHED не идёт; ABSORBED только при sha_before != sha_after, steps>0, ворота пройдены, тест есть (переименование не поглощение);
REMOVED только после ABSORBED и с чеком очистки (deleted_path, sha256, cause, replacement_id, time, evidence) + указатель повторной загрузки. Каждый переход после PROPOSED пишется в state/core/genesis_ledger.jsonl (hash-chain).
CLI: --list | --audit | --consent ID approved|denied [--nc-ok] | --rollback ID "причина". Решения Создателя вносятся только этой командой/чатом, модуль сам согласие не выдаёт. stdlib, MIT."""
import os, sys, json, time, fcntl
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C, nox_ledger as L
ORDER = ["PROPOSED", "FETCHED", "VERIFIED", "ACTIVE_ADAPTER", "TRAINING", "ABSORBED", "REMOVED"]
CLEAN = ("MIT", "Apache-2.0", "CC-BY-4.0", "BSD-3-Clause", "BSD-2-Clause", "CC0-1.0", "ISC")
class AbsorbError(Exception): pass
def path(r=None): return C.S(r) + "/absorption_registry.json"
def hunt_path(r=None): return C.S(r) + "/hunt_requests.json"
def _locked(r, fn):
    os.makedirs(C.S(r), exist_ok=True)
    with open(path(r) + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX); try_ = fn(); fcntl.flock(lk, fcntl.LOCK_UN); return try_
def load(r=None): return C.load_json(path(r), {"items": {}}) or {"items": {}}
def license_class(lic):
    if lic in CLEAN: return "clean"
    s = (lic or "").lower()
    if "nc" in s.replace("-", " ").split() or "-nc" in s or "noncommercial" in s: return "blocked_nc"
    return "needs_creator"
def propose(cid, name, repo, source, lic, r=None, t=None):
    def f():
        d = load(r)
        if cid in d["items"]: return d["items"][cid]
        it = {"id": cid, "name": name, "repo": repo, "source": source, "license": lic, "license_class": license_class(lic), "status": "PROPOSED", "consent": "pending", "creator_nc_ok": False, "history": [{"ts": C.iso_z(t), "to": "PROPOSED"}]}
        d["items"][cid] = it; C.atomic_json(path(r), d); return it
    return _locked(r, f)
def _set_hunt_status(r, cid, status):
    d = C.load_json(hunt_path(r), None)
    if not isinstance(d, dict): return False
    ok = False
    for q in d.get("requests", []):
        if q.get("id") == cid: q["status"] = status; q["decided_ts"] = C.iso_z(); ok = True
    if ok: C.atomic_json(hunt_path(r), d)
    return ok
def consent(cid, decision, by="Создатель", nc_ok=False, r=None, t=None):
    """Решение Создателя по кандидату. Пишет в реестр, hunt_requests и Ledger. Загрузку НЕ запускает."""
    if decision not in ("approved", "denied"): raise AbsorbError("decision")
    def f():
        d = load(r); it = d["items"].get(cid)
        if not it: raise AbsorbError("нет кандидата " + cid)
        it["consent"] = decision; it["creator_nc_ok"] = bool(nc_ok and decision == "approved"); it["history"].append({"ts": C.iso_z(t), "consent": decision, "by": by})
        C.atomic_json(path(r), d); return it
    it = _locked(r, f); _set_hunt_status(r, cid, "approved_by_creator" if decision == "approved" else "denied_by_creator")
    L.append("hunt_consent", {"id": cid, "name": it["name"], "decision": decision, "by": by, "license": it["license"], "nc_ok": it["creator_nc_ok"]}, r=r, t=t)
    return it
def _need(ev, keys, to):
    miss = [k for k in keys if ev.get(k) in (None, "", [], {})]
    if miss: raise AbsorbError("%s: нет полей %s" % (to, ",".join(miss)))
def transition(cid, to, evidence=None, r=None, t=None):
    ev = evidence or {}
    def f():
        d = load(r); it = d["items"].get(cid)
        if not it: raise AbsorbError("нет записи " + cid)
        cur = it["status"]
        if cur not in ORDER or to not in ORDER or ORDER.index(to) != ORDER.index(cur) + 1: raise AbsorbError("переход %s -> %s не по порядку" % (cur, to))
        if to == "FETCHED" and it.get("consent") != "approved": raise AbsorbError("загрузка без согласия Создателя запрещена")
        if ORDER.index(to) >= 1 and it["license_class"] != "clean" and not it.get("creator_nc_ok"): raise AbsorbError("лицензия %s: нужно решение Создателя" % it["license"])
        if to == "VERIFIED": _need(ev, ("revision", "sha256"), to)
        if to == "ABSORBED":
            _need(ev, ("sha_before", "sha_after", "steps", "test_result", "gate_pass", "revision"), to)
            if ev["sha_before"] == ev["sha_after"] or not ev.get("weights_changed", True): raise AbsorbError("ABSORBED: веса не менялись (переименование не поглощение)")
            if ev["gate_pass"] is not True or not (isinstance(ev["steps"], (int, float)) and ev["steps"] > 0): raise AbsorbError("ABSORBED: ворота не пройдены или шагов нет")
        if to == "REMOVED":
            _need(ev, ("deleted_path", "sha256", "cause", "replacement_id", "time", "evidence", "reload_pointer"), to)
        it["status"] = to; it.setdefault("evidence", {}).update({k: v for k, v in ev.items()})
        it["history"].append({"ts": C.iso_z(t), "from": cur, "to": to}); C.atomic_json(path(r), d); return dict(it)
    it = _locked(r, f)
    data = {"id": cid, "teacher": it["name"], "repo": it["repo"], "status": to, "revision": it.get("evidence", {}).get("revision"), "sha_before": ev.get("sha_before"), "sha_after": ev.get("sha_after"),
            "steps": ev.get("steps"), "utc": C.iso_z(t), "test_result": ev.get("test_result"), "gate": ev.get("gate_pass"), "license": it["license"]}
    if to == "REMOVED": data["cleanup_receipt"] = {k: ev[k] for k in ("deleted_path", "sha256", "cause", "replacement_id", "time", "evidence", "reload_pointer")}
    if to in ("FETCHED", "VERIFIED"): data["sha256"] = ev.get("sha256")
    L.append("absorb_" + to.lower(), {k: v for k, v in data.items() if v is not None}, r=r, t=t)
    return it
def rollback(cid, reason, evidence=None, r=None, t=None):
    """Откат: запись-указатель (восстановить веса на sha_before). Сами веса не трогаем."""
    def f():
        d = load(r); it = d["items"].get(cid)
        if not it or it["status"] not in ("TRAINING", "ABSORBED", "REMOVED"): raise AbsorbError("откат возможен из TRAINING/ABSORBED/REMOVED")
        prev = it["status"]; it["status"] = "ROLLED_BACK"; it["history"].append({"ts": C.iso_z(t), "from": prev, "to": "ROLLED_BACK", "reason": reason[:200]})
        C.atomic_json(path(r), d); return dict(it), prev
    it, prev = _locked(r, f)
    L.append("absorb_rollback", {"id": cid, "teacher": it["name"], "from": prev, "restore_sha": (it.get("evidence") or {}).get("sha_before"), "reason": reason[:200], "evidence": evidence or {}}, r=r, t=t)
    return it
def audit(r=None):
    """Проверка канона: загрузок без согласия 0; все переходы в Ledger; цепочка sha_before/sha_after."""
    d = load(r); led = L.read_all(r); logged = {(e["data"].get("id"), e["event"]) for e in led}
    no_consent = [i for i, it in d["items"].items() if ((it["status"] in ORDER and ORDER.index(it["status"]) >= 1) or it["status"] == "ROLLED_BACK") and it.get("consent") != "approved"] if d["items"] else []
    missing = []
    for i, it in d["items"].items():
        for h in it["history"]:
            if h.get("to") and h["to"] not in ("PROPOSED",) and h["to"] != "ROLLED_BACK" and (i, "absorb_" + h["to"].lower()) not in logged: missing.append((i, h["to"]))
    ab = sorted([it for it in d["items"].values() if (it.get("evidence") or {}).get("sha_after") and it["status"] in ("ABSORBED", "REMOVED")], key=lambda x: x["history"][-1]["ts"])
    broken = sum(1 for a, b in zip(ab, ab[1:]) if b["evidence"].get("sha_before") != a["evidence"].get("sha_after"))
    return {"items": len(d["items"]), "downloads_without_consent": len(no_consent), "not_in_ledger": len(missing), "sha_chain_breaks": broken, "ledger_ok": L.verify(r)[0]}
if __name__ == "__main__":
    a = sys.argv[1:]
    if "--consent" in a:
        i = a.index("--consent"); print(json.dumps(consent(a[i + 1], a[i + 2], nc_ok="--nc-ok" in a)["consent"]))
    elif "--rollback" in a:
        i = a.index("--rollback"); print(rollback(a[i + 1], a[i + 2])["status"])
    elif "--list" in a:
        for k, v in load()["items"].items(): print(k, v["status"], v["license"], v["consent"])
    else: print(json.dumps(audit()))
