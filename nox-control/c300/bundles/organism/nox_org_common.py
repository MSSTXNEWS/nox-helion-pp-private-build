#!/usr/bin/env python3
"""NOX организм: общие утилиты (только stdlib). Атомарная запись, хвост jsonl, журнал-сигналы с id, поиск записи по id."""
import os, json, time, hashlib, datetime as dt, fcntl
MSK = dt.timezone(dt.timedelta(hours=3))
def root(): return os.environ.get("NOX_ROOT", "/workspace/nox")
def S(r=None): return (r or root()) + "/state/core"
def M(r=None): return (r or root()) + "/state/mind"
def clip(x, a=0.0, b=1.0): return a if x < a else b if x > b else x
def iso_msk(t=None): return dt.datetime.fromtimestamp(t if t is not None else time.time(), MSK).isoformat(timespec="seconds")
def iso_z(t=None): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t if t is not None else time.time()))
def parse_ts(v):
    if isinstance(v, (int, float)): return float(v)
    if not isinstance(v, str) or not v: return 0.0
    try:
        s = v.strip().replace("Z", "+00:00")
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
        return d.timestamp()
    except Exception: return 0.0
def msk_hour(t=None): return dt.datetime.fromtimestamp(t if t is not None else time.time(), MSK).hour
def in_quiet(t=None):
    h = msk_hour(t); return h >= 23 or h < 8
def load_json(p, default=None):
    try:
        with open(p, encoding="utf-8") as f: return json.load(f)
    except Exception: return default
def atomic_json(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = "%s.tmp%d" % (p, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, p)
def jl_tail(p, n=200, maxbytes=400000):
    try:
        sz = os.path.getsize(p)
        with open(p, "rb") as f:
            f.seek(max(0, sz - maxbytes)); data = f.read().decode("utf-8", "ignore")
    except Exception: return []
    L = data.splitlines()
    if sz > maxbytes and L: L = L[1:]
    out = []
    for l in L[-n:]:
        try: d = json.loads(l)
        except Exception: continue
        if isinstance(d, dict): out.append(d)
    return out
def jl_append(p, obj, cap_bytes=0):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(p, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX); f.write(line); fcntl.flock(f, fcntl.LOCK_UN)
    if cap_bytes:
        try:
            if os.path.getsize(p) > cap_bytes:
                L = open(p, encoding="utf-8", errors="ignore").read().splitlines()
                keep = L[-max(1, len(L) // 2):]
                tmp = p + ".rot%d" % os.getpid(); open(tmp, "w", encoding="utf-8").write("\n".join(keep) + "\n"); os.replace(tmp, p)
        except Exception: pass
def legacy_ref(line_obj):
    """id для старых записей журнала без id: jr:<sha1 канонической строки>[:10]"""
    return "jr:" + hashlib.sha1(json.dumps(line_obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]
def emit_signal(r, sid, metric, value, sev=2, src_ref=None, st=None, t=None, reuse_s=1800, reuse_dv=0.1):
    """Записать сигнал в state/core/journal.jsonl (kind=organism, с id). Повторное значение того же sid в пределах reuse_s и reuse_dv даёт прежний id (журнал не засоряется)."""
    t = t if t is not None else time.time(); cache = st.setdefault("sig_last", {}) if st is not None else {}
    c = cache.get(sid)
    if c and t - c["t"] < reuse_s and abs(float(value) - c["v"]) < reuse_dv and c.get("ref") == src_ref: return c["id"]
    h = hashlib.sha1(("%s|%s|%.4f|%s" % (sid, t, value, src_ref)).encode()).hexdigest()[:8]
    sid_id = "sig_%s_%s" % (time.strftime("%Y%m%dT%H%M%S", time.gmtime(t)), h)
    rec = {"ts": iso_msk(t), "kind": "organism", "id": sid_id, "sid": sid, "metric": metric, "value": round(float(value), 4), "sev": sev, "msg": "сигнал " + sid}
    if src_ref: rec["src_ref"] = src_ref
    jl_append(S(r) + "/journal.jsonl", rec)
    cache[sid] = {"t": t, "v": float(value), "id": sid_id, "ref": src_ref}
    return sid_id
def resolve(r, cid, tail=20000):
    """Найти запись журнала по id (sig_* или jr:<sha>). None, если нет."""
    for d in reversed(jl_tail(S(r) + "/journal.jsonl", tail, maxbytes=8_000_000)):
        if d.get("id") == cid: return d
        if cid.startswith("jr:") and "id" not in d and legacy_ref(d) == cid: return d
    return None
