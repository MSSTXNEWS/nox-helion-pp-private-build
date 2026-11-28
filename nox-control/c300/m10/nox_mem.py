#!/usr/bin/env python3
"""NOX S03 memory service v2 (M10, 28.11), :18220. Based on v1 (mem0 prompt + bge-m3 :8082 + bge-reranker-v2-m3 :8083 + sqlite-vec).
M10 additions (additive only): provenance, [m:id] cites+verify, conflict registry, bi-temporal facts (m10_tfact), forgetting pass (archive w/ sha, nothing deleted),
hybrid recall (vec + FTS5 -> RRF -> rerank, abs threshold, time window). Never logs memory text.
POST /recall {q,user,cid,incognito,k,cite,debug} ; /remember ; /add_fact {fact,user,prov,ts} ; /forget ; /list ; /get {ids,user}
     /verify {answer,user,allowed_ids} ; /conflicts {user?} ; /conflict/resolve {id,keep:new|old|both,wrong} ; /asof {user,ts,tx?,pred?}
     /forget_pass {dry,apply} ; /owner_questions ; GET /health /stats"""
import json, os, re, sqlite3, struct, threading, time, hashlib, queue, gzip, math, urllib.request as ur
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import sqlite_vec
HERE = os.path.dirname(os.path.abspath(__file__)); import sys; sys.path.insert(0, HERE)
import m10_logic as L, m10_cite as CT
STATE = os.environ.get("NOX_STATE", "/workspace/nox/state")
DB = os.environ.get("NOX_S03_DB", STATE + "/core/s03.db")
PORT = int(os.environ.get("NOX_MEM_PORT", "18220"))
EMB = os.environ.get("NOX_EMB", "http://127.0.0.1:8082/embed"); RER = os.environ.get("NOX_RER", "http://127.0.0.1:8083/rerank"); LLM = "http://127.0.0.1:8104/v1/chat/completions"
SLOT = int(os.environ.get("NOX_MEM_SLOT", "3"))
K_VEC = 20; K_FTS = 20; K_OUT = 4; DUP = 0.90
ABS_DEF = float(os.environ.get("NOX_MEM_ABS", "0.08")); REL = 0.4
QDIR = STATE + "/core/m10_owner_questions.json"; ARCH = STATE + "/core/s03_archive"
LAST_RECALL = 0.0; LOCK = threading.Lock(); Q = queue.Queue(maxsize=50); USEQ = queue.Queue(maxsize=500)

def conn():
    c = sqlite3.connect(DB, timeout=10); c.enable_load_extension(True); sqlite_vec.load(c); c.enable_load_extension(False); return c
NEWCOLS = [("prov", "TEXT"), ("prov_src", "TEXT"), ("kind", "TEXT"), ("weight", "REAL"), ("repeats", "INTEGER DEFAULT 0"), ("uses", "INTEGER DEFAULT 0"), ("last_used", "REAL"), ("archived", "INTEGER DEFAULT 0"), ("valid_from", "REAL"), ("valid_to", "REAL")]
def init():
    c = conn()
    c.execute("create table if not exists s03_mem(id integer primary key, user text, cid text, status text default 'active', ts real)")
    c.execute("create table if not exists s03_journal(ts real, op text, id integer, n integer)")
    have = {r[1] for r in c.execute("pragma table_info(s03_mem)")}
    for n, t in NEWCOLS:
        if n not in have: c.execute("alter table s03_mem add column %s %s" % (n, t))
    c.execute("""create table if not exists m10_tfact(id integer primary key autoincrement, user text, mem_id integer, pred text, obj_key text, obj text, pol integer,
        valid_from real, valid_to real, tx_from real, tx_to real, superseded_by integer)""")
    c.execute("create index if not exists m10_tfact_u on m10_tfact(user,pred)")
    c.execute("""create table if not exists m10_conflicts(id integer primary key autoincrement, ts real, user text, new_id integer, old_id integer, kind text, pred text,
        status text default 'open', question text, asked_ts real, resolved_ts real, resolution text)""")
    c.execute("create table if not exists m10_archive(id integer primary key autoincrement, mem_id integer, sha text, file text, file_sha text, ts real)")
    c.execute("create table if not exists m10_goals(id integer primary key autoincrement, text text)")
    c.commit()
    # backfill (only NULL columns of s03_mem; s03 itself is never touched)
    c.execute("update s03_mem set prov='heard', prov_src=user where prov is null")
    c.execute("update s03_mem set valid_from=ts where valid_from is null")
    c.execute("update s03_mem set weight=? where weight is null and user='owner'", (1.0,))
    c.execute("update s03_mem set weight=0.8 where weight is null")
    rows = c.execute("select m.id, s.text, s.source from s03_mem m join s03 s on s.id=m.id where m.kind is null").fetchall()
    for i, t, src in rows: c.execute("update s03_mem set kind=? where id=?", (L.kind_of(t or "", src or ""), i))
    have_t = {r[0] for r in c.execute("select distinct mem_id from m10_tfact")}
    for i, t, src in c.execute("select m.id, s.text, s.source from s03_mem m join s03 s on s.id=m.id where m.status='active'").fetchall():
        if i in have_t or not t: continue
        u, ts = c.execute("select user, ts from s03_mem where id=?", (i,)).fetchone()
        for p, k, o, pol in L.triples(t): c.execute("insert into m10_tfact(user,mem_id,pred,obj_key,obj,pol,valid_from,tx_from) values(?,?,?,?,?,?,?,?)", (u, i, p, k, o, pol, ts, ts))
    if not c.execute("select 1 from m10_goals").fetchone():
        for g in ("благо Создателя и его семьи", "жизнь, обучение и рост NOX", "честность и память о близких людях"): c.execute("insert into m10_goals(text) values(?)", (g,))
    c.commit(); c.close()
def post(url, obj, timeout):
    rq = ur.Request(url, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
    with ur.urlopen(rq, timeout=timeout) as r: return json.loads(r.read())
def embed(texts, timeout=2.0): return post(EMB, {"texts": texts}, timeout)["vectors"]
def blob(v): return struct.pack("%df" % len(v), *v)
CFG_DEF = {"abs": 0.003, "simmin": 0.45, "rel": 0.25}
def _cfg():
    try: d = dict(CFG_DEF); d.update(json.load(open(STATE + "/s03_m10.json"))); return d
    except Exception: return dict(CFG_DEF)
def _inq(n): return ",".join("?" * n)

def recall(q, user, k=K_OUT, debug=False):
    t0 = time.time(); c = conn()
    try:
        n = c.execute("select count(*) from s03_mem where user=? and status='active' and coalesce(archived,0)=0", (user,)).fetchone()[0]
        if not n: return [], 0, []
        global LAST_RECALL; LAST_RECALL = time.time()
        v = embed([q[:500]], 0.25)[0]
        rows = c.execute("select id, distance from s03_vec where emb match ? and k=?", (blob(v), K_VEC + 20)).fetchall()
        okq = lambda ids: {r[0] for r in c.execute("select id from s03_mem where user=? and status='active' and coalesce(archived,0)=0 and id in (%s)" % _inq(len(ids)), [user] + list(ids))} if ids else set()
        okv = okq([r[0] for r in rows])
        vec = [(i, d) for i, d in rows if i in okv][:K_VEC]
        sim = {i: 1 - d * d / 2 for i, d in vec}
        # FTS5 prefix candidates (stems)
        fts = []; st = list(dict.fromkeys(L.stems(q)))[:12]
        if st:
            try:
                m = " OR ".join('"%s"*' % s.replace('"', "") for s in st)
                fr = [r[0] for r in c.execute("select rowid from s03_fts where s03_fts match ? order by bm25(s03_fts) limit 60", (m,))]
                okf = okq(fr); fts = [i for i in fr if i in okf][:K_FTS]
            except Exception: fts = []
        tw = L.time_window(q); win = []
        if tw:
            win = [r[0] for r in c.execute("select id from s03_mem where user=? and status='active' and coalesce(archived,0)=0 and ts between ? and ? order by ts limit 20", (user, tw[0], tw[1]))]
        rrf = {}
        for lst in ([i for i, _ in vec], fts, win):
            for r_, i in enumerate(lst): rrf[i] = rrf.get(i, 0.0) + 1.0 / (60 + r_)
        for i in win: rrf[i] += 0.02   # temporal boost
        cand = [i for i, _ in sorted(rrf.items(), key=lambda x: -x[1])][:24]
        if not cand: return [], 0, []
        txt = {r[0]: r[1] for r in c.execute("select id, text from s03 where id in (%s)" % _inq(len(cand)), cand)}
        cand = [i for i in cand if txt.get(i)]
        docs = [txt[i] for i in cand]
        try: sc = post(RER, {"q": q[:500], "docs": docs}, 0.12)["scores"]; reranked = True
        except Exception: sc = [max(0.0, sim.get(i, 0.3)) for i in cand]; reranked = False
        best = sorted(zip(sc, cand, docs), key=lambda x: ((x[1] in set(win)) if win else 0, x[0]), reverse=True)   # time-anchored question: window items first
        top = max([x[0] for x in best] or [0]) if best else 0; thr = float(open(STATE + "/s03_sim").read()) if os.path.exists(STATE + "/s03_sim") else 0.80
        cf = _cfg(); winset = set(win)
        gate = (not reranked) or top >= cf["abs"] or max([sim.get(i, 0.0) for i in cand] or [0]) >= cf["simmin"] or bool(winset)
        dbg = [(i, round(s, 4), round(sim.get(i, -1), 3), i in fts, i in winset) for s, i, _ in best[:12]] if debug else []
        out = [(round(s, 3), i, d, round(sim.get(i, 0.0), 3)) for s, i, d in best if gate and ((s >= cf["rel"] * top) or sim.get(i, 0) >= thr or i in winset)][:(max(k, 6) if winset else k)]
        return out, int((time.time() - t0) * 1000), dbg
    finally: c.close()

def _annot(c, ids, cite):
    """-> {id: suffix} (provenance + open conflicts)"""
    if not ids: return {}
    m = {r[0]: r[1:] for r in c.execute("select id,prov,prov_src from s03_mem where id in (%s)" % _inq(len(ids)), ids)}
    cf = set()
    for a, b in c.execute("select new_id, old_id from m10_conflicts where status='open' and (new_id in (%s) or old_id in (%s))" % (_inq(len(ids)), _inq(len(ids))), ids + ids): cf.add(a); cf.add(b)
    o = {}
    for i in ids:
        p, s = m.get(i, (None, None)); suf = ""
        if p in ("web", "advisor"): suf += " (источник: %s, не подтверждено)" % ("интернет" if p == "web" else "советник")
        elif p == "thought": suf += " (моя мысль, не проверено)"
        if i in cf: suf += " (есть противоречие, не утверждай как факт)"
        o[i] = suf
    return o
def _use_note(ids):
    for i in ids:
        try: USEQ.put_nowait(i)
        except queue.Full: break
def use_worker():
    while True:
        i = USEQ.get(); ids = [i]
        try:
            while len(ids) < 20: ids.append(USEQ.get(timeout=0.5))
        except queue.Empty: pass
        try:
            with LOCK:
                c = conn(); c.executemany("update s03_mem set uses=coalesce(uses,0)+1, last_used=? where id=?", [(time.time(), x) for x in ids]); c.commit(); c.close()
        except Exception: pass

def _write_questions():
    try:
        c = conn(); rows = c.execute("select id, ts, user, question from m10_conflicts where status='open' order by ts limit 5").fetchall(); c.close()
        os.makedirs(os.path.dirname(QDIR), exist_ok=True)
        tmp = QDIR + ".tmp"; open(tmp, "w").write(json.dumps({"ts": time.time(), "open": [{"id": r[0], "ts": r[1], "user": r[2], "question": r[3]} for r in rows]}, ensure_ascii=False)); os.replace(tmp, QDIR)
    except Exception as e: print("q write err", type(e).__name__, flush=True)

def add_fact(fact, user, cid="", src="chat", prov=None, ts=None):
    fact = fact.strip()
    if len(fact) < 6: return None
    pv, ps = L.prov_norm(prov, user); v = embed([fact], 5.0)[0]; now = ts or time.time(); newc = 0
    with LOCK:
        c = conn()
        try:
            r = c.execute("select id, distance from s03_vec where emb match ? and k=5", (blob(v),)).fetchall()
            tr = L.triples(fact)
            # slot conflicts first: a correction must not be dropped as a "duplicate"
            conf = []
            for p, k, o, pol in tr:
                for oid, otext, ots in c.execute("select t.mem_id, s.text, m.ts from m10_tfact t join s03_mem m on m.id=t.mem_id join s03 s on s.id=t.mem_id where t.user=? and t.pred=? and t.tx_to is null and t.valid_to is null and m.status='active'", (user, p)).fetchall():
                    if L.conflicts(otext or "", fact): conf.append((oid, otext, ots, p))
            if not conf:
                for i, d in r:
                    if 1 - d * d / 2 >= DUP and c.execute("select 1 from s03_mem where id=? and user=? and status='active'", (i, user)).fetchone():
                        c.execute("update s03_mem set repeats=coalesce(repeats,0)+1 where id=?", (i,)); c.commit(); return -i
            sha = hashlib.sha256((user + "|" + fact + (("|" + str(ts)) if ts else "")).encode()).hexdigest()
            ex = c.execute("select s.id from s03 s join s03_mem m on m.id=s.id where s.sha=? and m.status='active'", (sha,)).fetchone()
            if ex: c.execute("update s03_mem set repeats=coalesce(repeats,0)+1 where id=?", (ex[0],)); c.commit(); return -ex[0]
            cur = c.execute("insert or ignore into s03(ts,source,owner,text,sha) values(?,?,?,?,?)", (time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)), src + ":" + cid[:40], user, fact, sha))
            if not cur.lastrowid or cur.rowcount == 0: c.commit(); return None
            i = cur.lastrowid; kd = L.kind_of(fact, src)
            c.execute("insert into s03_fts(rowid,text) values(?,?)", (i, fact))
            c.execute("insert into s03_vec(id,emb) values(?,?)", (i, blob(v)))
            c.execute("insert into s03_mem(id,user,cid,ts,prov,prov_src,kind,weight,valid_from) values(?,?,?,?,?,?,?,?,?)", (i, user, cid, now, pv, ps, kd, L.prov_weight(pv, ps), now))
            for p, k, o, pol in tr: c.execute("insert into m10_tfact(user,mem_id,pred,obj_key,obj,pol,valid_from,tx_from) values(?,?,?,?,?,?,?,?)", (user, i, p, k, o, pol, now, time.time()))
            seen = set()
            for oid, otext, ots, p in conf:
                if oid in seen: continue
                seen.add(oid)
                kind = L.conflicts(otext, fact)[0][0]
                c.execute("insert into m10_conflicts(ts,user,new_id,old_id,kind,pred,question) values(?,?,?,?,?,?,?)", (time.time(), user, i, oid, kind, p, L.question(otext or "", fact, ots, now, user))); newc += 1
            c.execute("insert into s03_journal values(?,?,?,?)", (time.time(), "add", i, newc))
            c.commit()
        finally: c.close()
    if newc: _write_questions()
    return i

def resolve(cid_, keep, wrong=False):
    with LOCK:
        c = conn()
        try:
            r = c.execute("select new_id, old_id, status from m10_conflicts where id=?", (cid_,)).fetchone()
            if not r or r[2] != "open": return {"ok": False, "error": "not_open"}
            new, old, _ = r; now = time.time()
            nv = c.execute("select valid_from from s03_mem where id=?", (new,)).fetchone()[0] or now
            if keep == "new":
                c.execute("update s03_mem set status='superseded', valid_to=? where id=?", (nv, old))
                if wrong: c.execute("update m10_tfact set tx_to=?, superseded_by=? where mem_id=? and tx_to is null", (now, new, old))
                else: c.execute("update m10_tfact set valid_to=?, superseded_by=? where mem_id=? and valid_to is null", (nv, new, old))
            elif keep == "old":
                c.execute("update s03_mem set status='rejected' where id=?", (new,)); c.execute("update m10_tfact set tx_to=? where mem_id=? and tx_to is null", (now, new))
            elif keep != "both": return {"ok": False, "error": "bad_keep"}
            c.execute("update m10_conflicts set status='resolved', resolved_ts=?, resolution=? where id=?", (now, keep + ("/wrong" if wrong else ""), cid_))
            c.execute("insert into s03_journal values(?,?,?,?)", (now, "resolve:" + keep, cid_, 1)); c.commit()
        finally: c.close()
    _write_questions(); return {"ok": True}

def _scrub_archive(c, ids):
    """forget of an archived record: remove it from archive files, update file sha (archive is a copy, S03 rows are blanked by forget())"""
    for f, in c.execute("select distinct file from m10_archive where mem_id in (%s)" % _inq(len(ids)), ids).fetchall():
        try:
            rows = [json.loads(l) for l in gzip.open(f, "rt", encoding="utf-8")]; keep = [r for r in rows if r["id"] not in ids]
            tmp = f + ".tmp"
            with gzip.open(tmp, "wt", encoding="utf-8") as w:
                for r in keep: w.write(json.dumps(r, ensure_ascii=False) + "\n")
            os.replace(tmp, f); fs = hashlib.sha256(open(f, "rb").read()).hexdigest()
            c.execute("update m10_archive set file_sha=? where file=?", (fs, f))
        except Exception as e: print("scrub err", type(e).__name__, flush=True)

def forget(user=None, mid=None):
    with LOCK:
        c = conn(); c.isolation_level = None
        try:
            if mid: ids = [r[0] for r in c.execute("select id from s03_mem where id=? and user=?", (mid, user))] if user else [mid]
            else: ids = [r[0] for r in c.execute("select id from s03_mem where user=? and status in ('active','superseded','rejected')", (user,))]
            trg = c.execute("select name,sql from sqlite_master where type='trigger' and tbl_name='s03'").fetchall()
            c.execute("BEGIN")
            try:
                for i in ids:
                    row = c.execute("select text from s03 where id=?", (i,)).fetchone()
                    if row and row[0]: c.execute("insert into s03_fts(s03_fts,rowid,text) values('delete',?,?)", (i, row[0]))
                    c.execute("delete from s03_vec where id=?", (i,))
                    c.execute("update s03_mem set status='forgotten' where id=?", (i,))
                if ids:
                    for nme, _ in trg: c.execute('drop trigger "%s"' % nme)
                    c.execute("update s03 set text='', sha='forgotten-'||id where id in (%s)" % _inq(len(ids)), ids)
                    for _, sql in trg: c.execute(sql)
                    c.execute("delete from m10_tfact where mem_id in (%s)" % _inq(len(ids)), ids)           # derived index of the forgotten text
                    c.execute("update m10_conflicts set status='forgotten', question='' where (new_id in (%s) or old_id in (%s)) and status!='forgotten'" % (_inq(len(ids)), _inq(len(ids))), ids + ids)
                    _scrub_archive(c, ids)
                c.execute("insert into s03_journal values(?,?,?,?)", (time.time(), "forget", mid or 0, len(ids)))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK"); raise
        finally: c.close()
    _write_questions(); return len(ids)

def list_facts(user, n=50, q=""):
    c = conn()
    try: rows = c.execute("select s.id, m.ts, s.text, m.prov, m.prov_src from s03 s join s03_mem m on m.id=s.id where m.user=? and m.status='active' order by s.id desc", (user,)).fetchall()
    finally: c.close()
    if q:
        toks = [t.lower()[:5] for t in re.findall(r"\w{3,}", q)]
        rows = [r for r in rows if any(t in r[2].lower() for t in toks)]
    return [{"id": r[0], "ts": r[1], "text": r[2], "kind": "fact", "sensitive": 0, "prov": r[3], "prov_src": r[4]} for r in rows[:n]]
def get_records(ids):
    if not ids: return {}
    c = conn()
    try: return {r[0]: {"text": r[1], "user": r[2], "status": r[3], "prov": r[4], "ts": r[5]} for r in c.execute("select s.id, s.text, m.user, m.status, m.prov, m.ts from s03 s join s03_mem m on m.id=s.id where s.id in (%s)" % _inq(len(ids)), list(ids))}
    finally: c.close()
def rerank_fn(q, docs): return post(RER, {"q": q[:500], "docs": docs}, 0.3)["scores"]
def asof(user, ts, tx=None, pred=None):
    c = conn()
    try:
        sql = "select t.mem_id, t.pred, t.obj, t.pol, t.valid_from, t.valid_to from m10_tfact t where t.user=? and t.valid_from<=? and (t.valid_to is null or t.valid_to>?) and t.tx_from<=? and (t.tx_to is null or t.tx_to>?)"
        a = [user, ts, ts, tx or time.time(), tx or time.time()]
        if pred: sql += " and t.pred=?"; a.append(pred)
        return [{"id": r[0], "pred": r[1], "obj": r[2], "pol": r[3], "valid_from": r[4], "valid_to": r[5]} for r in c.execute(sql + " order by t.valid_from", a)]
    finally: c.close()

def goal_vecs():
    c = conn(); g = [r[0] for r in c.execute("select text from m10_goals")]; c.close()
    try:
        p = STATE + "/m10_goals.txt"
        if os.path.exists(p): g += [x.strip() for x in open(p, encoding="utf-8") if x.strip()][:20]
    except Exception: pass
    return embed(g, 5.0)
def forget_pass(apply=False, now=None):
    """score = weight x repeat x goal_link x recency. Archive (mark + gz copy with sha) for age>30d & low score. Protected kinds / pinned never touched. Nothing deleted."""
    now = now or time.time(); gv = goal_vecs(); stat = {"scanned": 0, "protected": 0, "young": 0, "kept": 0, "archived": 0, "ids": []}
    c = conn()
    try:
        rows = c.execute("select m.id, m.kind, m.weight, m.repeats, m.uses, m.ts, s.text from s03_mem m join s03 s on s.id=m.id where m.status='active' and coalesce(m.archived,0)=0").fetchall()
        sel = []
        for i, kd, w, rp, us, ts, tx in rows:
            stat["scanned"] += 1
            if kd in L.PROTECTED: stat["protected"] += 1; continue
            age = (now - (ts or now)) / 86400.0
            if age < 30: stat["young"] += 1; continue
            e = c.execute("select emb from s03_vec where id=?", (i,)).fetchone()
            goal = 0.5
            if e:
                vv = struct.unpack("%df" % 1024, e[0]); goal = max(0.0, max(sum(a * b for a, b in zip(vv, g)) for g in gv))
            sc = L.keep_score(w or 0.5, rp, us, min(1.0, 0.3 + goal), age)
            if sc < 0.12: sel.append((i, tx, sc))
            else: stat["kept"] += 1
        stat["archived"] = len(sel); stat["ids"] = [i for i, _, _ in sel][:50]
        if apply and sel:
            os.makedirs(ARCH, exist_ok=True); f = "%s/arch_%s.jsonl.gz" % (ARCH, time.strftime("%Y%m%d_%H%M%S", time.localtime(now)))
            with gzip.open(f, "wt", encoding="utf-8") as w:
                for i, tx, sc in sel: w.write(json.dumps({"id": i, "sha": hashlib.sha256(tx.encode()).hexdigest(), "text": tx, "score": round(sc, 4)}, ensure_ascii=False) + "\n")
            fs = hashlib.sha256(open(f, "rb").read()).hexdigest()
            with LOCK:
                for i, tx, sc in sel:
                    c.execute("update s03_mem set archived=1 where id=?", (i,)); c.execute("insert into m10_archive(mem_id,sha,file,file_sha,ts) values(?,?,?,?,?)", (i, hashlib.sha256(tx.encode()).hexdigest(), f, fs, now))
                c.execute("insert into s03_journal values(?,?,?,?)", (now, "archive", 0, len(sel))); c.commit()
            stat["file_sha"] = fs[:12]
        return stat
    finally: c.close()

_FP = None
def fact_prompt():
    global _FP
    if _FP is None:
        from mem0.configs.prompts import FACT_RETRIEVAL_PROMPT as P; _FP = P
    return _FP
def extract(text, ans):
    body = {"model": "x", "messages": [{"role": "system", "content": fact_prompt()}, {"role": "user", "content": "Input:\nuser: %s\nassistant: %s\n\nПравила: извлеки ВСЕ факты о пользователе из реплики user (имя, возраст, вкусы, планы, близкие). Пиши каждый факт по-русски, отдельной короткой фразой в третьем лице («Пользователя зовут ...», «Пользователь не любит ...»). Ответ только JSON {\"facts\": [...]}." % (text[:1500], ans[:300])}],
            "max_tokens": 400, "temperature": 0.0, "id_slot": SLOT, "cache_prompt": True, "response_format": {"type": "json_object"}, "chat_template_kwargs": {"enable_thinking": False}}
    r = post(LLM, body, 60.0); s = r["choices"][0]["message"]["content"]
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S); m = re.search(r"\{.*\}", s, re.S)
    f = json.loads(m.group(0)).get("facts", []) if m else []
    return [str(x) for x in f if isinstance(x, str)][:6]
def worker():
    while True:
        text, ans, user, cid = Q.get()
        _tg = time.time()   # V1_02: extraction only when idle. Rollback: touch state/chat_v102.off
        while time.time() - max(LAST_RECALL, _tg) < (12 if os.path.exists(STATE + "/chat_v102.off") else 22): time.sleep(1)
        try:
            for f in extract(text, ans): add_fact(f, user, cid, prov="heard:" + user)
            _pend_drop(user, text)
        except Exception as e: print("extract err", type(e).__name__, flush=True)
def gate(text): return len(text) >= 20 and not text.startswith("/")
PEND = {}
def _pend_add(user, t):
    if os.path.exists(STATE + "/chat_v102.off"): return
    Lp = PEND.setdefault(user, []); Lp.append((time.time(), t[:300])); del Lp[:-4]
def _pend_drop(user, t):
    Lp = PEND.get(user) or []; PEND[user] = [x for x in Lp if x[1] != t[:300]]
def _pend_ctx(user, ctx):
    Lp = [x[1] for x in (PEND.get(user) or []) if time.time() - x[0] < 600]
    if not Lp: return ctx
    add = "Недавно собеседник сказал (ещё не сохранено): " + " | ".join(Lp)
    return (ctx + "\n" + add) if ctx else ("Из твоей долговременной памяти (недавно, ещё не сохранено): " + add)

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _j(self, o, c=200):
        raw = json.dumps(o, ensure_ascii=False).encode(); self.send_response(c); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/health":
            c = conn(); n = c.execute("select count(*) from s03_mem where status='active'").fetchone()[0]; oc = c.execute("select count(*) from m10_conflicts where status='open'").fetchone()[0]; c.close()
            return self._j({"ok": True, "facts": n, "queue": Q.qsize(), "v": "m10", "open_conflicts": oc})
        if p == "/stats":
            c = conn(); o = {"status": dict(c.execute("select status,count(*) from s03_mem group by status")), "prov": dict(c.execute("select prov,count(*) from s03_mem group by prov")), "kind": dict(c.execute("select kind,count(*) from s03_mem group by kind")),
                             "tfact": c.execute("select count(*) from m10_tfact").fetchone()[0], "conflicts": dict(c.execute("select status,count(*) from m10_conflicts group by status")), "archived": c.execute("select count(*) from m10_archive").fetchone()[0]}; c.close(); return self._j(o)
        if p == "/owner_questions":
            try: return self._j(json.load(open(QDIR)))
            except Exception: return self._j({"open": []})
        self._j({"error": "nf"}, 404)
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try: b = json.loads(self.rfile.read(n) or b"{}")
        except ValueError: return self._j({"error": "bad_json"}, 400)
        p = self.path.split("?")[0]; user = str(b.get("user") or "owner")[:64]; cid = str(b.get("cid") or "")
        try:
            if p == "/recall":
                if b.get("incognito") or not b.get("q"): return self._j({"context": "", "hits": 0, "ms": 0})
                hits4, ms, dbg = recall(str(b["q"]), user, int(b.get("k") or K_OUT), bool(b.get("debug")))
                hits = [(a, b_, c_) for a, b_, c_, _ in hits4]; ids = [i for _, i, _ in hits]
                if ids: _use_note(ids)
                c = conn()
                try: an = _annot(c, ids, bool(b.get("cite")))
                finally: c.close()
                cite = bool(b.get("cite"))
                ctx = ("Из твоей долговременной памяти (ты это помнишь о собеседнике; говори естественно, как помнящий человек, без оговорок про «контекст» и «данные»; используй только если уместно" + ("; ссылайся на запись как [m:id], когда пересказываешь конкретный факт о прошлом" if cite else "") + "):\n" + "\n".join("- " + (("[m:%d] " % i) if cite else "") + d + an.get(i, "") for _, i, d in hits)) if hits else ""
                ctx = _pend_ctx(user, ctx)
                o = {"context": ctx, "hits": len(hits), "ids": ids, "scores": [x for x, _, _ in hits], "sims": [h[3] for h in hits4], "ms": ms}
                if b.get("debug"): o["debug"] = dbg
                return self._j(o)
            if p == "/remember":
                t = str(b.get("text") or "")
                if b.get("incognito") or not gate(t): return self._j({"queued": False})
                _pend_add(user, t)
                try: Q.put_nowait((t, str(b.get("answer") or ""), user, cid)); return self._j({"queued": True})
                except queue.Full: return self._j({"queued": False})
            if p == "/list": return self._j({"items": list_facts(user, int(b.get("n") or 50), str(b.get("q") or ""))})
            if p == "/get": return self._j({"records": {str(k): v for k, v in get_records([int(x) for x in (b.get("ids") or [])][:50]).items() if (not b.get("user") or v["user"] == b.get("user"))}})
            if p == "/add_fact": return self._j({"id": add_fact(str(b.get("fact") or ""), user, cid, "api", b.get("prov"), float(b["ts"]) if b.get("ts") else None)})
            if p == "/forget": return self._j({"deleted": forget(user if (b.get("all_user") or b.get("id")) else None, int(b["id"]) if b.get("id") else None) if (b.get("all_user") or b.get("id")) else 0})
            if p == "/verify":
                allowed = b.get("allowed_ids"); allowed = set(int(x) for x in allowed) if allowed is not None else None
                v = CT.verify(str(b.get("answer") or ""), get_records, allowed, user if b.get("user") else None, rerank_fn if b.get("rerank", True) else None); return self._j(v)
            if p == "/conflicts":
                c = conn()
                try: rows = c.execute("select id,ts,user,new_id,old_id,kind,pred,status,question from m10_conflicts where status=? " + ("and user=?" if b.get("user") else "") + " order by ts limit 50", [b.get("status") or "open"] + ([b["user"]] if b.get("user") else [])).fetchall()
                finally: c.close()
                return self._j({"items": [dict(zip(("id", "ts", "user", "new_id", "old_id", "kind", "pred", "status", "question"), r)) for r in rows]})
            if p == "/conflict/resolve": return self._j(resolve(int(b["id"]), str(b.get("keep")), bool(b.get("wrong"))))
            if p == "/asof": return self._j({"items": asof(user, float(b.get("ts") or time.time()), float(b["tx"]) if b.get("tx") else None, b.get("pred"))})
            if p == "/forget_pass": return self._j(forget_pass(bool(b.get("apply")) and not b.get("dry", True), float(b["now"]) if b.get("now") else None))
        except Exception as e:
            import traceback; print(traceback.format_exc()[-600:], flush=True); return self._j({"error": type(e).__name__}, 500)
        self._j({"error": "nf"}, 404)
if __name__ == "__main__":
    init(); threading.Thread(target=worker, daemon=True).start(); threading.Thread(target=use_worker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
