echo "K1: l2_mem_dep3"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; V=$N/venv_mem; D=$N/svc/mem; mkdir -p $D $N/svc/logs
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
        if not cand: return [], 0
        txt = {r[0]: r[1] for r in c.execute("select id, text from s03 where id in (%s)" % ",".join("?" * len(cand)), [i for i, _ in cand])}
        docs = [txt[i] for i, _ in cand if i in txt]; cid_ = [i for i, _ in cand if i in txt]
        try: sc = post(RER, {"q": q[:500], "docs": docs}, 0.12)["scores"]
        except Exception: sc = [1 - d * d / 2 for i, d in cand if i in txt]; 
        best = sorted(zip(sc, cid_, docs), reverse=True)[:k]
        return [(round(s, 3), i, d) for s, i, d in best if s >= MIN_SCORE], int((time.time() - t0) * 1000)
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
        c = conn()
        try:
            if mid: ids = [r[0] for r in c.execute("select id from s03_mem where id=? and user=?", (mid, user))] if user else [mid]
            else: ids = [r[0] for r in c.execute("select id from s03_mem where user=? and status='active'", (user,))]
            for i in ids:
                row = c.execute("select text from s03 where id=?", (i,)).fetchone()
                if row: c.execute("insert into s03_fts(s03_fts,rowid,text) values('delete',?,?)", (i, row[0]))
                c.execute("delete from s03_vec where id=?", (i,)); c.execute("update s03 set text='' where id=?", (i,))
                c.execute("update s03_mem set status='forgotten' where id=?", (i,))
            c.execute("insert into s03_journal values(?,?,?,?)", (time.time(), "forget", mid or 0, len(ids))); c.commit(); return len(ids)
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
                hits, ms = recall(str(b["q"]), user, int(b.get("k") or K_OUT))
                ctx = ("Из твоей долговременной памяти (факты о собеседнике; используй, только если уместно, не пересказывай списком):\n" + "\n".join("- " + d for _, _, d in hits)) if hits else ""
                return self._j({"context": ctx, "hits": len(hits), "ids": [i for _, i, _ in hits], "ms": ms})
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
cat > $D/nox_rerank.py <<'PYEOF'
#!/usr/bin/env python3
"""bge-reranker-v2-m3 on GPU fp16, :8083. POST /rerank {q,docs}->{scores} (sigmoid)."""
import json, os, torch
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from transformers import AutoTokenizer, AutoModelForSequenceClassification
P = "/workspace/nox/models/warm/BAAI/bge-reranker-v2-m3"; DEV = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(P); m = AutoModelForSequenceClassification.from_pretrained(P, torch_dtype=torch.float16 if DEV == "cuda" else torch.float32).to(DEV).eval()
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def _j(self, o):
        raw = json.dumps(o).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self): self._j({"ok": True, "dev": DEV})
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        d = [str(x)[:600] for x in (b.get("docs") or [])][:40]
        if not d: return self._j({"scores": []})
        with torch.no_grad():
            e = tok([[str(b.get("q", ""))[:500], x] for x in d], padding=True, truncation=True, max_length=256, return_tensors="pt").to(DEV)
            s = torch.sigmoid(m(**e).logits.view(-1).float()).cpu().tolist()
        self._j({"scores": s})
ThreadingHTTPServer(("127.0.0.1", 8083), H).serve_forever()
PYEOF
cp -n $N/state/core/s03.db $N/state/core/s03.db.bak_l2 2>/dev/null
# reranker (main venv, torch)
pkill -f svc/mem/nox_mem.py; sleep 1
setsid nohup $V/bin/python $D/nox_mem.py >$N/svc/logs/mem.log 2>&1 < /dev/null &
for i in $(seq 1 40); do curl -s -m 2 127.0.0.1:8083/ >/dev/null && curl -s -m 2 127.0.0.1:18220/health && break; sleep 3; done; echo
tail -n 12 $N/svc/logs/mem.log | cut -c1-200
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
$V/bin/python - <<'PY'
import json,time,urllib.request as ur,statistics
def P(u,o,t=30):
    rq=ur.Request("http://127.0.0.1:"+u,data=json.dumps(o).encode(),headers={"Content-Type":"application/json"})
    return json.loads(ur.urlopen(rq,timeout=t).read())
U="qa-mem1"
for f in ["У пользователя есть кошка по имени Мурка","Пользователь живёт в городе Севастополь","Пользователь любит чёрный кофе без сахара","Пользователь работает инженером","Пользователь планирует отпуск в сентябре","Любимый цвет пользователя синий"]:
    print("add",P("18220/add_fact",{"fact":f,"user":U}))
print("dup",P("18220/add_fact",{"fact":"У пользователя есть кошка по имени Мурка","user":U}))
for q in ["как зовут мою кошку?","какой кофе я пью","где я живу","привет как дела"]:
    P("18220/recall",{"q":q,"user":U})
qs=["как зовут мою кошку?","какой кофе я пью","где я живу","какой у меня любимый цвет","когда мой отпуск","кем я работаю","что у меня за питомец","привет, как дела"]*4
lat=[];hits=[]
for q in qs:
    t=time.time(); r=P("18220/recall",{"q":q,"user":U}); lat.append((time.time()-t)*1000); hits.append(r["hits"])
lat.sort(); print("recall ms p50=%d p95=%d max=%d n=%d"%(statistics.median(lat),lat[int(len(lat)*.95)-1],lat[-1],len(lat)))
r=P("18220/recall",{"q":"как зовут мою кошку?","user":U}); print("top:",r["context"].replace("\n"," | ")[:300],"ms",r["ms"])
r=P("18220/recall",{"q":"привет, как дела","user":U}); print("smalltalk hits",r["hits"])
print("incog",P("18220/recall",{"q":"кошка","user":U,"incognito":True}))
print("other user",P("18220/recall",{"q":"кошка","user":"qa-other"})["hits"])
t=time.time(); print("remember",P("18220/remember",{"text":"Меня зовут Тест, мне 41 год, и я терпеть не могу грибы","answer":"Понял.","user":"qa-mem2","cid":"qa-c"}))
for i in range(30):
    time.sleep(2); h=json.loads(ur.urlopen("http://127.0.0.1:18220/health").read())
    r=P("18220/recall",{"q":"что я не люблю есть","user":"qa-mem2"})
    if r["hits"]: break
print("extract_wait_s",int(time.time()-t),"hits",r["hits"],r["context"].replace("\n"," | ")[:300])
print("forget",P("18220/forget",{"user":U,"all_user":True}),P("18220/forget",{"user":"qa-mem2","all_user":True}))
print("after forget",P("18220/recall",{"q":"кошка","user":U})["hits"])
PY
tail -3 $N/svc/logs/mem.log | cut -c1-200
