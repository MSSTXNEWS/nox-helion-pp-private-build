#!/usr/bin/env python3
"""Genesis Ledger: hash-chain, append-only, state/core/genesis_ledger.jsonl. Каждая запись: n, ts, event, data, prev_sha, sha.
sha = sha256(prev_sha + "\n" + канонический JSON {n,ts,event,data}). Первая запись «зачатие»: дата первого запуска (phase.json), утверждение паспорта 28.11 по поручению, md5 паспорта.
Рождение (event=birth) пишет только ритуал: append(..., by_ritual=True). Этот модуль born_at НЕ читает и НЕ меняет.
CLI: --conceive (идемпотентно) | --verify | --tail. Старые genesis_ledger.json / genesis_chain.jsonl не трогаются (хвост старой цепи вписывается в зачатие как ссылка)."""
import os, sys, json, time, hashlib, fcntl, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C
ZERO = "0" * 64
RITUAL_ONLY = ("birth",)
def path(r=None): return C.S(r) + "/genesis_ledger.jsonl"
def _sha(prev, body): return hashlib.sha256((prev + "\n" + json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()
def read_all(r=None):
    out = []
    try:
        for l in open(path(r), encoding="utf-8"):
            l = l.strip()
            if l: out.append(json.loads(l))
    except FileNotFoundError: pass
    return out
def verify(r=None):
    """-> (ok, n_records, ошибка|None)"""
    prev = ZERO; L = read_all(r)
    for i, e in enumerate(L):
        if e.get("n") != i: return False, len(L), "n@%d" % i
        if e.get("prev_sha") != prev: return False, len(L), "prev@%d" % i
        if _sha(prev, {"n": e["n"], "ts": e["ts"], "event": e["event"], "data": e["data"]}) != e.get("sha"): return False, len(L), "sha@%d" % i
        prev = e["sha"]
    return True, len(L), None
def append(event, data, by_ritual=False, r=None, t=None):
    if event in RITUAL_ONLY and not by_ritual: raise PermissionError("событие %s пишет только ритуал" % event)
    p = path(r); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0); lines = [l for l in f.read().splitlines() if l.strip()]
        prev, n = ZERO, 0
        if lines:
            last = json.loads(lines[-1]); prev, n = last["sha"], last["n"] + 1
        body = {"n": n, "ts": C.iso_msk(t), "event": event, "data": data}
        rec = dict(body, prev_sha=prev, sha=_sha(prev, body))
        f.seek(0, 2); f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"); f.flush(); os.fsync(f.fileno())
        fcntl.flock(f, fcntl.LOCK_UN)
    return rec
def first_launch_date(r=None):
    """Дата первого запуска из phase.json: дата ts минус days_alive."""
    ph = C.load_json(C.M(r) + "/phase.json", {}) or {}
    t = C.parse_ts(ph.get("ts")); da = ph.get("days_alive")
    if not t or not isinstance(da, (int, float)): return None
    return (dt.datetime.fromtimestamp(t, dt.timezone.utc) - dt.timedelta(days=int(da))).date().isoformat()
def conceive(r=None):
    """Первая запись «зачатие». Идемпотентна: если журнал уже есть, ничего не пишет."""
    if read_all(r): return None
    pp = C.S(r) + "/passport.json"
    try: md5 = hashlib.md5(open(pp, "rb").read()).hexdigest()
    except Exception: md5 = None
    P = C.load_json(pp, {}) or {}; ap = P.get("approval") or {}
    legacy = None
    for d in C.jl_tail(C.S(r) + "/genesis_chain.jsonl", 1):
        legacy = d.get("hash")
    data = {"first_launch_date": first_launch_date(r), "first_launch_source": "phase.json: дата ts минус days_alive",
            "passport_approval": {"by": ap.get("by"), "date": ap.get("date"), "scope": ap.get("scope"), "revocable": ap.get("revocable"), "on_instruction_of_creator": True},
            "passport_md5": md5, "legacy_chain_last_hash": legacy, "born": False}
    return append("conception", data, r=r)
if __name__ == "__main__":
    a = sys.argv[1:] or ["--verify"]
    if "--conceive" in a:
        rec = conceive(); print("conceived" if rec else "already", (rec or {}).get("sha", "")[:12])
    ok, n, err = verify(); print("verify ok=%s n=%d err=%s" % (ok, n, err))
    if "--tail" in a:
        for e in read_all()[-3:]: print(e["n"], e["event"], e["sha"][:12], e["prev_sha"][:12])
    sys.exit(0 if ok else 2)
