echo "K1: l2_mem_dep10"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; V=$N/venv_mem; D=$N/svc/mem
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
LOCK = threading.Lock(); Q = queue.Queue(maxsize=50)

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
        v = embed([q[:500]], 0.15)[0]
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
        thr = float(open('/workspace/nox/state/s03_sim').read()) if os.path.exists('/workspace/nox/state/s03_sim') else 0.55
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
                ctx = ("Из твоей долговременной памяти (факты о собеседнике; используй, только если уместно, не пересказывай списком):\n" + "\n".join("- " + d for _, _, d in hits)) if hits else ""
                return self._j({"context": ctx, "hits": len(hits), "ids": [i for _, i, _ in hits], "scores": [x for x, _, _ in hits], "sims": [h[3] for h in hits4], "ms": ms})
            if p == "/remember":
                t = str(b.get("text") or "")
                if b.get("incognito") or not gate(t): return self._j({"queued": False})
                try: Q.put_nowait((t, str(b.get("answer") or ""), user, cid)); return self._j({"queued": True})
                except queue.Full: return self._j({"queued": False})
            if p == "/add_fact": return self._j({"id": add_fact(str(b.get("fact") or ""), user, cid, "api")})
            if p == "/forget": return self._j({"deleted": forget(user if (b.get("all_user") or b.get("id")) else None, int(b["id"]) if b.get("id") else None) if (b.get("all_user") or b.get("id")) else 0})
        except Exception as e:
            import traceback; print(traceback.format_exc()[-600:], flush=True); return self._j({"error": type(e).__name__}, 500)
        self._j({"error": "nf"}, 404)
if __name__ == "__main__":
    init(); threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", 18220), H).serve_forever()
PYEOF
pkill -f svc/mem/nox_mem.py; sleep 1
setsid nohup $V/bin/python $D/nox_mem.py >$N/svc/logs/mem.log 2>&1 < /dev/null &
for i in $(seq 1 20); do curl -s -m 2 127.0.0.1:18220/health && break; sleep 2; done; echo
F=$N/web/pkg/server/chat_core.py
cat > /tmp/patch_fast_l2.py <<'PYEOF'
F = "/workspace/nox/web/pkg/server/chat_core.py"; s = open(F).read()
if "S03_FAST" in s: print("already")
else:
    a = '        msgs = sysm + rest + [{"role": "user", "content": up_text}]\n'
    assert s.count(a) == 1
    b = '''        _mem = next((str(m.get("content") or "") for m in history if m.get("role") == "system" and "долговременной памяти" in str(m.get("content") or "")), "")   # S03_FAST: память в хвост хода, префикс кэша не ломается
        _mem = _mem[_mem.index("Из твоей долговременной памяти"):][:900] if _mem else ""
        msgs = sysm + rest + [{"role": "user", "content": (_mem + "\\n\\n---\\n" + up_text) if _mem else up_text}]
'''
    open(F, "w").write(s.replace(a, b)); print("patched fast")
PYEOF
python3 /tmp/patch_fast_l2.py
python3 -m py_compile $F && echo compiled || { cp $F.bak_l2_s03 $F; echo ROLLED_BACK; }
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 20
$V/bin/python - <<'PY'
import json,time,http.client,urllib.request as ur,statistics
def P(u,o):
    rq=ur.Request("http://127.0.0.1:"+u,data=json.dumps(o).encode(),headers={"Content-Type":"application/json"}); return json.loads(ur.urlopen(rq,timeout=20).read())
U="qa-e2e3"
for f in ["Пользователя зовут Тест","Пользователь живёт в Севастополе","У пользователя есть кошка по имени Мурка","Пользователь не любит грибы","Пользователю 41 год"]: P("18220/add_fact",{"fact":f,"user":U})
lat=[]
for q in ["Как зовут мою кошку и где я живу?","как зовут мою кошку","что я не люблю","привет, как дела","Расскажи коротко про луну","напиши функцию сортировки на питоне","сколько мне лет и как меня зовут"]*3:
    t=time.time(); r=P("18220/recall",{"q":q,"user":U}); lat.append((time.time()-t)*1000)
    if len(lat)<=7: print(q,"|",r["hits"],r["scores"],r["sims"])
lat.sort(); print("recall ms p50=%d p95=%d max=%d"%(statistics.median(lat),lat[int(len(lat)*.95)-1],lat[-1]))
def turn(cid,q):
    t0=time.time(); c=http.client.HTTPConnection("127.0.0.1",18091,timeout=90)
    c.request("POST","/api/turn",body=json.dumps({"conversation_id":cid,"message":q,"user_id":U},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"})
    r=c.getresponse(); txt="";first=None
    while True:
        l=r.readline()
        if not l: break
        try:o=json.loads(l)
        except Exception: continue
        if o.get("t")=="delta":
            if first is None: first=time.time()-t0
            txt+=o.get("text","")
        if o.get("t")=="done": break
    return round(first or -1,2),txt[:300].replace("\n"," ")
print(turn("qa-e2e3-b","Как зовут мою кошку и где я живу?"))
print(turn("qa-e2e3-c","Расскажи коротко про луну"))
print(P("18220/forget",{"user":U,"all_user":True}))
PY
echo "--- log"; tail -n 4 $N/state/s03_recall.log
