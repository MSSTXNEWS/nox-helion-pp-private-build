# -*- coding: utf-8 -*-
"""restore_full: пробное восстановление «души» (канон гл. 1: восстановление за <= 2 ч, проверка раз в неделю). Ничего живого не меняет, пишет только в /tmp и в отчёт.
Шаги: 1) архив soul_hNN.tgz (паспорт, genesis ledger/chain, passport_prompt, canon-файлы): распаковать в /tmp, сверить sha с MANIFEST.json внутри и с живыми файлами;
2) зашифрованная копия soul_cfg_hNN.tgz.age: расшифровать ключом canon/age_private.key (age), распаковать, проверить, что паспорт читается как JSON;
3) цепочка genesis_chain.jsonl из восстановленной копии: проверка хэшей и связей prev; 4) S03: снимок sqlite (онлайн-backup API) -> gzip в canon/soul/s03_snap_<день недели>.sqlite3.gz (7 слотов, ротация по дню недели), затем восстановление в /tmp, integrity_check, число записей против живой базы.
Отчёт: state/core/restore_full.json (только числа/имена/да-нет), canon/restore_full_ok.json. Цель: total_s <= 7200.
Запуск: python3 -I restore_full.py [--snapshot] | --daemon (снимок S03 ежедневно 02:10 UTC, полный тест по воскресеньям 01:20 UTC). Флаг state/restore_full.off -> выход."""
import os, sys, json, time, glob, gzip, shutil, tarfile, sqlite3, hashlib, tempfile, subprocess
N = os.environ.get("NOX_ROOT", "/workspace/nox"); C = N + "/canon"; SOUL = C + "/soul"; S = N + "/state/core"
S03_DBS = [S + "/s03.db"] + sorted(p for p in glob.glob(N + "/svc/mem/*.db") if not p.endswith(("-wal", "-shm")))
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()
def safe_extract(tg, dst):
    with tarfile.open(tg) as t:
        ms = [m for m in t.getmembers() if not (m.name.startswith("/") or ".." in m.name.split("/")) and (m.isfile() or m.isdir())]
        t.extractall(dst, members=ms, filter="data") if hasattr(tarfile, "data_filter") else t.extractall(dst, members=ms)
    return len(ms)
def newest(pat): 
    L = sorted(glob.glob(pat), key=os.path.getmtime); return L[-1] if L else None
def snapshot_s03(out_dir=SOUL, dbs=None, now=None):
    """Ежедневный снимок S03: онлайн-backup (согласованная копия при работающем сервисе) + gzip. -> список {db, bytes, ok}."""
    res = []; wd = time.strftime("%a", time.gmtime(now)).lower(); os.makedirs(out_dir, exist_ok=True)
    for i, db in enumerate(dbs if dbs is not None else S03_DBS):
        if not os.path.exists(db): continue
        tmp = os.path.join(out_dir, ".snap_%d.tmp" % i); dst = os.path.join(out_dir, "s03_snap_%d_%s.sqlite3.gz" % (i, wd))
        try:
            src = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=30); d = sqlite3.connect(tmp); src.backup(d); d.close(); src.close()
            with open(tmp, "rb") as f, gzip.open(dst + ".part", "wb", 6) as g: shutil.copyfileobj(f, g)
            os.replace(dst + ".part", dst); res.append({"db": os.path.basename(db), "bytes": os.path.getsize(dst), "ok": True})
        except Exception as e: res.append({"db": os.path.basename(db), "ok": False, "err": type(e).__name__})
        finally:
            try: os.remove(tmp)
            except Exception: pass
    return res
def chain_ok(path):
    prev = None; n = 0
    for l in open(path, encoding="utf-8"):
        l = l.strip()
        if not l: continue
        e = json.loads(l); n += 1
        h = hashlib.sha256(json.dumps({k: e[k] for k in ("n", "ts", "event", "data", "prev")}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if e.get("hash") != h or (prev is not None and e.get("prev") != prev): return False, n
        prev = e.get("hash")
    return True, n
def run(out=None):
    out = out or (S + "/restore_full.json"); T0 = time.time(); r = {"ts": int(T0), "steps": {}, "ok": False, "target_s": 7200}; tmp = tempfile.mkdtemp(prefix="rfull_")
    def step(name, fn):
        t = time.time()
        try: v = fn()
        except Exception as e: v = {"ok": False, "err": type(e).__name__ + ": " + str(e)[:80]}
        v["s"] = round(time.time() - t, 2); r["steps"][name] = v; return v
    def s_tgz():
        p = newest(SOUL + "/soul_h*.tgz")
        if not p: return {"ok": False, "err": "нет soul_hNN.tgz"}
        d = os.path.join(tmp, "soul"); os.makedirs(d); n = safe_extract(p, d); man = json.load(open(d + "/MANIFEST.json")); bad = same = diff = missing = 0
        for path, h in man.items():
            q = d + path if path.startswith("/") else os.path.join(d, path)
            if not os.path.exists(q): q = os.path.join(d, path.lstrip("/"))
            if not os.path.exists(q) or sha(q) != h: bad += 1; continue
            if not os.path.exists(path): missing += 1
            elif sha(path) == h: same += 1
            else: diff += 1
        return {"ok": bad == 0 and len(man) > 0, "archive": os.path.basename(p), "age_h": round((time.time() - os.path.getmtime(p)) / 3600, 1), "files": n, "manifest": len(man), "bad_sha": bad, "same_as_live": same, "differs_from_live": diff, "not_in_live": missing, "bytes": os.path.getsize(p)}
    def s_cfg():
        p = newest(SOUL + "/soul_cfg_h*.tgz.age")
        if not p: return {"ok": False, "err": "нет soul_cfg_hNN.tgz.age"}
        dec = os.path.join(tmp, "cfg.tgz"); k = C + "/age_private.key"
        rc = subprocess.run(["age", "-d", "-i", k, "-o", dec, p], capture_output=True, timeout=120).returncode
        if rc: return {"ok": False, "err": "age rc=%d" % rc}
        d = os.path.join(tmp, "cfg"); os.makedirs(d); n = safe_extract(dec, d); pj = glob.glob(d + "/**/passport.json", recursive=True)
        fields = len(json.load(open(pj[0]))) if pj else 0; ch = glob.glob(d + "/**/genesis_chain.jsonl", recursive=True)
        return {"ok": n > 0 and fields > 0, "archive": os.path.basename(p), "files": n, "passport_fields": fields, "has_chain": bool(ch), "bytes": os.path.getsize(p)}
    def s_chain():
        ch = glob.glob(tmp + "/**/genesis_chain.jsonl", recursive=True)
        if not ch: return {"ok": False, "err": "цепочки нет в копиях"}
        ok, n = chain_ok(ch[0]); live = S + "/genesis_chain.jsonl"; ln = sum(1 for l in open(live) if l.strip()) if os.path.exists(live) else None
        return {"ok": ok, "entries": n, "live_entries": ln}
    def s_s03():
        sn = snapshot_s03(); res = []
        for i, db in enumerate(S03_DBS):
            p = newest(SOUL + "/s03_snap_%d_*.sqlite3.gz" % i)
            if not p or not os.path.exists(db): continue
            dst = os.path.join(tmp, "s03_%d.sqlite3" % i)
            with gzip.open(p, "rb") as f, open(dst, "wb") as g: shutil.copyfileobj(f, g)
            c = sqlite3.connect(dst); integ = c.execute("pragma integrity_check").fetchone()[0]; tabs = [x[0] for x in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' and name not like '%_fts%'")]
            rows = sum(c.execute('select count(*) from "%s"' % t).fetchone()[0] for t in tabs[:40]); c.close()
            l = sqlite3.connect("file:%s?mode=ro" % db, uri=True); lrows = sum(l.execute('select count(*) from "%s"' % t).fetchone()[0] for t in tabs[:40] if l.execute("select 1 from sqlite_master where name=?", (t,)).fetchone()); l.close()
            res.append({"db": os.path.basename(db), "integrity": integ, "tables": len(tabs), "rows": rows, "live_rows": lrows, "ok": integ == "ok" and rows > 0 and rows >= 0.9 * lrows})
        return {"ok": bool(res) and all(x["ok"] for x in res), "snapshots": sn, "restored": res}
    def s_canon():
        files = [C + "/canon.py", C + "/autonomy_matrix.json", C + "/RUNBOOK_CANON.md"]; ex = [f for f in files if os.path.exists(f)]
        return {"ok": len(ex) >= 2, "present": len(ex), "sha_prefix": {os.path.basename(f): sha(f)[:12] for f in ex}}
    for nm, fn in (("soul_tgz", s_tgz), ("soul_cfg_age", s_cfg), ("genesis_chain", s_chain), ("s03_sqlite", s_s03), ("canon_files", s_canon)): step(nm, fn)
    shutil.rmtree(tmp, ignore_errors=True)
    r["total_s"] = round(time.time() - T0, 1); r["ok"] = all(v.get("ok") for v in r["steps"].values()) and r["total_s"] <= r["target_s"]; r["failed"] = [k for k, v in r["steps"].items() if not v.get("ok")]
    for p in (out, C + "/restore_full_ok.json"):
        try: os.makedirs(os.path.dirname(p), exist_ok=True); json.dump(r, open(p, "w"), ensure_ascii=False, indent=1)
        except Exception: pass
    return r
def daemon():
    last_snap = last_full = None
    while True:
        try:
            g = time.gmtime(); day = time.strftime("%F", g)
            if os.path.exists(N + "/state/restore_full.off"): time.sleep(600); continue
            if g.tm_hour == 2 and g.tm_min >= 10 and last_snap != day: snapshot_s03(); last_snap = day
            if g.tm_wday == 6 and g.tm_hour == 1 and g.tm_min >= 20 and last_full != day: run(); last_full = day
        except Exception: pass
        time.sleep(120)
if __name__ == "__main__":
    if "--daemon" in sys.argv: daemon()
    elif "--snapshot" in sys.argv: print(json.dumps(snapshot_s03(), ensure_ascii=False))
    else:
        if os.path.exists(N + "/state/restore_full.off"): print('{"skipped":"flag off"}'); sys.exit(0)
        r = run(); print(json.dumps(r, ensure_ascii=False)); sys.exit(0 if r["ok"] else 1)
