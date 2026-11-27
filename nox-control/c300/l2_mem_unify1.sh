echo "K1: l2_mem_unify1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; D=$N/svc/mem; LV=$N/svc/living
cp -n $N/state/living/mem.db $N/state/living/mem.db.bak_l2_unify
cp -n $N/state/core/s03.db $N/state/core/s03.db.bak_l2_unify
cat > $D/nox_mem.py <<'PYEOF'
#!/usr/bin/env python3
"""NOX S03 memory service (:18220). Engine: mem0 (Apache-2.0) extraction prompt + bge-m3 (:8082) + bge-reranker-v2-m3 (:8083) + sqlite-vec s03.db.
POST /recall {q,user,cid,incognito,k} -> {context,hits,ms}; POST /remember {text,answer,user,cid,incognito}; POST /add_fact {fact,user}; POST /forget {id|user|all_user}; GET /health /list?user=
Off switch: state/s03_recall.off (chat side). Never logs memory text."""
import json, os, re, sqlite3, struct, threading, time, hashlib, queue, urllib.request as ur
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import sqlite_vec
DB = os.environ.get("NOX_S03_DB", "/workspace/nox/state/core/s03.db")
EMB = "http://127.0.0.1:8082/embed"; RER = "http://127.0.0.1:8083/rerank"; LLM = "http://127.0.0.1:8104/v1/chat/completions"
SLOT = int(os.environ.get("NOX_MEM_SLOT", "3"))
K_VEC = 20; K_OUT = 4; MIN_SCORE = float(os.environ.get("NOX_MEM_MIN", "0.25")); DUP = 0.90
LAST_RECALL = 0.0; LOCK = threading.Lock(); Q = queue.Queue(maxsize=50)

def conn():
    c = sqlite3.connect(DB, timeout=10); c.enable_load_extension(True); sqlite_vec.load(c); c.enable_load_extension(False)
    return c
def init():
    c = conn()
    c.execute("create table if not exists s03_mem(id integer primary key, user text, cid text, status text default 'active', ts real)")
    c.execute("create table if not exists s03_journal(ts real, op text, id integer, n integer)")
    c.commit(); c.close()
def post(url, obj, timeout):
    rq = ur.Request(url, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
    with ur.urlopen(rq, timeout=timeout) as r: return json.loads(r.read())
def embed(texts, timeout=2.0): return post(EMB, {"texts": texts}, timeout)["vectors"]
def blob(v): return struct.pack("%df" % len(v), *v)
def recall(q, user, k=K_OUT):
    t0 = time.time(); c = conn()
    try:
        n = c.execute("select count(*) from s03_mem where user=? and status='active'", (user,)).fetchone()[0]
        if not n: return [], 0
        global LAST_RECALL; LAST_RECALL = time.time()
        v = embed([q[:500]], 0.25)[0]
        rows = c.execute("select id, distance from s03_vec where emb match ? and k=?", (blob(v), K_VEC + 20)).fetchall()
        ids = [r[0] for r in rows]
        if not ids: return [], 0
        ok = {r[0]: r[1] for r in c.execute("select id, 1 from s03_mem where user=? and status='active' and id in (%s)" % ",".join("?" * len(ids)), [user] + ids)}
        cand = [(i, d) for i, d in rows if i in ok][:K_VEC]
        sim = {i: 1 - d * d / 2 for i, d in cand}
        if not cand: return [], 0
        txt = {r[0]: r[1] for r in c.execute("select id, text from s03 where id in (%s)" % ",".join("?" * len(cand)), [i for i, _ in cand])}
        docs = [txt[i] for i, _ in cand if i in txt]; cid_ = [i for i, _ in cand if i in txt]
        try: sc = post(RER, {"q": q[:500], "docs": docs}, 0.12)["scores"]
        except Exception: sc = [1 - d * d / 2 for i, d in cand if i in txt]; 
        best = sorted(zip(sc, cid_, docs), reverse=True)[:k]
        top = best[0][0] if best else 0
        thr = float(open('/workspace/nox/state/s03_sim').read()) if os.path.exists('/workspace/nox/state/s03_sim') else 0.80
        out = [(round(s, 3), i, d, round(sim[i], 3)) for s, i, d in best if (s >= max(0.02, 0.4 * top)) or sim[i] >= thr]
        return out, int((time.time() - t0) * 1000)
    finally: c.close()
def add_fact(fact, user, cid="", src="chat"):
    fact = fact.strip()
    if len(fact) < 6: return None
    v = embed([fact], 5.0)[0]
    with LOCK:
        c = conn()
        try:
            r = c.execute("select id, distance from s03_vec where emb match ? and k=3", (blob(v),)).fetchall()
            for i, d in r:
                if 1 - d * d / 2 >= DUP and c.execute("select 1 from s03_mem where id=? and user=? and status='active'", (i, user)).fetchone(): return -i
            sha = hashlib.sha256((user + "|" + fact).encode()).hexdigest()
            cur = c.execute("insert or ignore into s03(ts,source,owner,text,sha) values(?,?,?,?,?)", (time.strftime("%Y-%m-%dT%H:%M:%S"), src + ":" + cid[:40], user, fact, sha))
            if not cur.lastrowid or cur.rowcount == 0: c.commit(); return None
            i = cur.lastrowid
            c.execute("insert into s03_fts(rowid,text) values(?,?)", (i, fact))
            c.execute("insert into s03_vec(id,emb) values(?,?)", (i, blob(v)))
            c.execute("insert into s03_mem(id,user,cid,ts) values(?,?,?,?)", (i, user, cid, time.time()))
            c.commit(); return i
        finally: c.close()
def forget(user=None, mid=None):
    with LOCK:
        c = conn(); c.isolation_level = None
        try:
            if mid: ids = [r[0] for r in c.execute("select id from s03_mem where id=? and user=?", (mid, user))] if user else [mid]
            else: ids = [r[0] for r in c.execute("select id from s03_mem where user=? and status='active'", (user,))]
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
                    c.execute("update s03 set text='', sha='forgotten-'||id where id in (%s)" % ",".join("?" * len(ids)), ids)
                    for _, sql in trg: c.execute(sql)
                c.execute("insert into s03_journal values(?,?,?,?)", (time.time(), "forget", mid or 0, len(ids)))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK"); raise
            return len(ids)
        finally: c.close()
def list_facts(user, n=50, q=""):
    c = conn()
    try:
        rows = c.execute("select s.id, m.ts, s.text from s03 s join s03_mem m on m.id=s.id where m.user=? and m.status='active' order by s.id desc", (user,)).fetchall()
    finally: c.close()
    if q:
        toks = [t.lower()[:5] for t in re.findall(r"\w{3,}", q)]
        rows = [r for r in rows if any(t in r[2].lower() for t in toks)]
    return [{"id": r[0], "ts": r[1], "text": r[2], "kind": "fact", "sensitive": 0} for r in rows[:n]]
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
        while time.time() - LAST_RECALL < 12: time.sleep(1)   # не мешать чату: эмбеддинг на том же GPU
        try:
            for f in extract(text, ans): add_fact(f, user, cid)
        except Exception as e: print("extract err", type(e).__name__, flush=True)
def gate(text): return len(text) >= 20 and not text.startswith("/")
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _j(self, o, c=200):
        raw = json.dumps(o, ensure_ascii=False).encode(); self.send_response(c); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/health":
            c = conn(); n = c.execute("select count(*) from s03_mem where status='active'").fetchone()[0]; c.close(); return self._j({"ok": True, "facts": n, "queue": Q.qsize()})
        self._j({"error": "nf"}, 404)
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try: b = json.loads(self.rfile.read(n) or b"{}")
        except ValueError: return self._j({"error": "bad_json"}, 400)
        p = self.path.split("?")[0]; user = str(b.get("user") or "owner")[:64]; cid = str(b.get("cid") or "")
        try:
            if p == "/recall":
                if b.get("incognito") or not b.get("q"): return self._j({"context": "", "hits": 0, "ms": 0})
                hits4, ms = recall(str(b["q"]), user, int(b.get("k") or K_OUT))
                hits = [(a, b, c) for a, b, c, _ in hits4]
                ctx = ("Из твоей долговременной памяти (ты это помнишь о собеседнике; говори естественно, как помнящий человек, без оговорок про «контекст» и «данные»; используй только если уместно):\n" + "\n".join("- " + d for _, _, d in hits)) if hits else ""
                return self._j({"context": ctx, "hits": len(hits), "ids": [i for _, i, _ in hits], "scores": [x for x, _, _ in hits], "sims": [h[3] for h in hits4], "ms": ms})
            if p == "/remember":
                t = str(b.get("text") or "")
                if b.get("incognito") or not gate(t): return self._j({"queued": False})
                try: Q.put_nowait((t, str(b.get("answer") or ""), user, cid)); return self._j({"queued": True})
                except queue.Full: return self._j({"queued": False})
            if p == "/list": return self._j({"items": list_facts(user, int(b.get("n") or 50), str(b.get("q") or ""))})
            if p == "/add_fact": return self._j({"id": add_fact(str(b.get("fact") or ""), user, cid, "api")})
            if p == "/forget": return self._j({"deleted": forget(user if (b.get("all_user") or b.get("id")) else None, int(b["id"]) if b.get("id") else None) if (b.get("all_user") or b.get("id")) else 0})
        except Exception as e:
            import traceback; print(traceback.format_exc()[-600:], flush=True); return self._j({"error": type(e).__name__}, 500)
        self._j({"error": "nf"}, 404)
if __name__ == "__main__":
    init(); threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", 18220), H).serve_forever()
PYEOF
supervisorctl restart nox_mem | tail -1; sleep 4; curl -s -m 3 127.0.0.1:18220/health; echo
python3 - <<'PY'
import sqlite3,json,urllib.request as ur
def P(u,o):
    rq=ur.Request("http://127.0.0.1:"+u,data=json.dumps(o).encode(),headers={"Content-Type":"application/json"}); return json.loads(ur.urlopen(rq,timeout=30).read())
rows=sqlite3.connect("/workspace/nox/state/living/mem.db").execute("select text from mem order by id").fetchall()
ok=dup=0
for (t,) in rows:
    r=P("18220/add_fact",{"fact":t,"user":"owner","cid":"migrated"}).get("id")
    if r and r>0: ok+=1
    else: dup+=1
print("mem.db rows",len(rows),"new",ok,"already/short",dup,"owner active in s03:",len(P("18220/list",{"user":"owner","n":100000})["items"]))
PY
cp -n $LV/living_svc.py $LV/living_svc.py.bak_l2_unify
cat > /tmp/patch_living_l2.py <<'PYEOF'
F = "/workspace/nox/svc/living/living_svc.py"; s = open(F).read()
if "S03_DELEGATE" in s: print("already")
else:
    for n in ("mem_add", "mem_search", "mem_list", "mem_forget"):
        a = "def %s(" % n; assert s.count(a) == 1; s = s.replace(a, "def %s_legacy(" % n)
    a = "def mem_search_clean(q, k=5):\n    return [r for r in mem_search(q, k)]"
    assert s.count(a) == 1
    add = '''# ---- S03_DELEGATE (LANE2): одна память = nox_mem :18220 (s03.db); флаг-откат: touch state/living/mem_legacy.on (вернёт старый mem.db) ----
import urllib.request as _ur3
def _legacy(): return os.path.exists("/workspace/nox/state/living/mem_legacy.on")
_CID = [""]
def _s3(path, obj, t=6.0):
    rq = _ur3.Request("http://127.0.0.1:18220" + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
    with _ur3.urlopen(rq, timeout=t) as r: return json.loads(r.read())
def _u(): return ("qa-" + _CID[0][:40]) if _CID[0].startswith("qa-") else "owner"
def mem_add(text, kind="fact"):
    if _legacy(): return mem_add_legacy(text, kind)
    text = text.strip()[:600]
    if len(text) < 3: return None, "пусто"
    i = _s3("/add_fact", {"fact": text, "user": _u(), "cid": _CID[0]}).get("id")
    if i is None: return None, "пусто"
    return (i, "ok") if i > 0 else (-i, "уже было")
def mem_search(q, k=5):
    if _legacy(): return mem_search_legacy(q, k)
    return _s3("/list", {"user": _u(), "n": k, "q": q}).get("items", [])
def mem_list(n=50):
    if _legacy(): return mem_list_legacy(n)
    return _s3("/list", {"user": _u(), "n": n}).get("items", [])
def mem_forget(mid=None, all_=False):
    if _legacy(): return mem_forget_legacy(mid, all_)
    return _s3("/forget", {"user": _u(), "all_user": True} if all_ else {"user": _u(), "id": int(mid)}).get("deleted", 0)
def mem_search_clean(q, k=5):
    return [r for r in mem_search(q, k)]'''
    s = s.replace(a, add)
    a = "    r = command(text, cid)\n"; assert s.count(a) == 1
    s = s.replace(a, "    _CID[0] = cid\n" + a)
    a = "    if not inc and b.get(\"mem\", True):\n"; assert s.count(a) == 1
    s = s.replace(a, "    if not inc and b.get(\"mem\", True) and _legacy():\n")
    a = "def mem_consolidate():\n"; assert s.count(a) == 1
    s = s.replace(a, a + "    if not _legacy(): return\n")
    open(F, "w").write(s); print("patched living")
PYEOF
python3 /tmp/patch_living_l2.py
python3 -m py_compile $LV/living_svc.py && echo compiled || { cp $LV/living_svc.py.bak_l2_unify $LV/living_svc.py; echo ROLLED_BACK; }
pkill -f "living_svc.py"; sleep 2
(cd $LV && nohup setsid $N/venv_living/bin/python living_svc.py >$LV/logs/living.log 2>&1 < /dev/null &)
for i in $(seq 1 15); do (echo > /dev/tcp/127.0.0.1/18215) 2>/dev/null && break; sleep 1; done
python3 - <<'PY'
import json,urllib.request as ur
def pre(t):
    rq=ur.Request("http://127.0.0.1:18215/pre",data=json.dumps({"text":t,"cid":"qa-liv1","mem":True,"emo":False}).encode(),headers={"Content-Type":"application/json"}); return json.loads(ur.urlopen(rq,timeout=20).read()).get("reply")
print(pre("/запомни Тестовый факт: у меня есть попугай Кеша"))
print(pre("/запомни Тестовый факт: у меня есть попугай Кеша"))
r=pre("/память"); print(r)
import re; n=re.search(r"#(\d+)",r).group(1)
print(pre("/память попугай"))
print(pre("/забудь "+n)); print(pre("/память"))
print(pre("/запомни Другой тестовый факт про рыбку")); print(pre("/забудь_всё да"))
PY
tail -n 3 $LV/logs/living.log | cut -c1-200
