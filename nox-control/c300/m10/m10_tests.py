# -*- coding: utf-8 -*-
"""functional tests of M10 on a BENCH instance (never prod). usage: m10_tests.py URL DB"""
import sys, json, time, sqlite3, gzip, hashlib, os, urllib.request as ur
U = sys.argv[1]; DBP = sys.argv[2]; ST = {"ok": 0, "bad": 0}
def P(path, o, t=15):
    rq = ur.Request(U + path, data=json.dumps(o).encode(), headers={"Content-Type": "application/json"}); return json.loads(ur.urlopen(rq, timeout=t).read())
def G(path): return json.loads(ur.urlopen(U + path, timeout=10).read())
def T(name, cond):
    ST["ok" if cond else "bad"] += 1; print(("PASS " if cond else "FAIL ") + name)
db = lambda q, a=(): sqlite3.connect(DBP).execute(q, a).fetchall()
n0 = db("select count(*) from s03")[0][0]
# 1 provenance
a = P("/add_fact", {"fact": "Пользователя зовут Тестер", "user": "tt", "prov": "heard:tt"})["id"]
b = P("/add_fact", {"fact": "Пользователь живёт в Омске", "user": "tt", "prov": "web"})["id"]
c_ = P("/add_fact", {"fact": "Пользователь, возможно, любит шахматы", "user": "tt", "prov": "thought"})["id"]
d_ = P("/add_fact", {"fact": "Пользователь изучает бухгалтерию", "user": "tt", "prov": "advisor"})["id"]
pv = {r[0]: (r[1], r[2]) for r in db("select id,prov,prov_src from s03_mem where user='tt'")}
T("prov heard/web/thought/advisor", pv[a] == ("heard", "tt") and pv[b][0] == "web" and pv[c_][0] == "thought" and pv[d_][0] == "advisor")
T("prov none missing", db("select count(*) from s03_mem where prov is null")[0][0] == 0)
r = P("/recall", {"q": "где живёт пользователь", "user": "tt", "cite": True})
T("recall web marked + [m:id]", ("[m:%d]" % b) in r["context"] and "интернет" in r["context"])
# 2 conflict: not silent
e = P("/add_fact", {"fact": "Пользователя зовут Иннокентий", "user": "tt"})["id"]
cf = P("/conflicts", {"user": "tt"})["items"]
T("conflict created", len(cf) == 1 and cf[0]["old_id"] == a and cf[0]["new_id"] == e)
T("old not overwritten", db("select status from s03_mem where id=?", (a,))[0][0] == "active" and db("select text from s03 where id=?", (a,))[0][0] == "Пользователя зовут Тестер")
q = G("/owner_questions"); T("owner question written", len(q["open"]) >= 1 and "Что верно" in q["open"][0]["question"])
P("/add_fact", {"fact": "Пользователя зовут Иннокентий", "user": "tt"}); T("repeat not a new conflict", len(P("/conflicts", {"user": "tt"})["items"]) == 1)
r = P("/recall", {"q": "как зовут пользователя", "user": "tt"}); T("open conflict flagged in recall", "противоречие" in r["context"])
t_mid = time.time()
T("resolve new", P("/conflict/resolve", {"id": cf[0]["id"], "keep": "new"})["ok"])
T("old superseded not deleted", db("select status from s03_mem where id=?", (a,))[0][0] == "superseded" and db("select count(*) from s03 where id=?", (a,))[0][0] == 1)
now_names = [x["obj"] for x in P("/asof", {"user": "tt", "pred": "name"})["items"]]; T("asof now = new", now_names == ["иннокентий"])
past = [x["obj"] for x in P("/asof", {"user": "tt", "pred": "name", "ts": db("select valid_from from s03_mem where id=?", (e,))[0][0] - 0.01})["items"]]; T("asof past = old (bi-temporal)", past == ["тестер"])
T("open questions emptied", len(G("/owner_questions")["open"]) == 0)
# polarity
P("/add_fact", {"fact": "Пользователь любит кинзу", "user": "tt"}); P("/add_fact", {"fact": "Пользователь не любит кинзу", "user": "tt"})
T("polarity conflict", any(x["kind"] == "polarity" for x in P("/conflicts", {"user": "tt"})["items"]))
# 3 verify
ids = [x["id"] for x in P("/list", {"user": "tt"})["items"]]
v = P("/verify", {"answer": "Ты говорил, что живёшь в Омске [m:%d]." % b, "user": "tt", "rerank": False}); T("verify ok cite", v["ok"])
v = P("/verify", {"answer": "Ты говорил, что любишь рыбалку [m:%d]." % b, "user": "tt", "rerank": False}); T("verify unsupported cite", not v["ok"] and v["cites"][0]["status"] == "unsupported")
v = P("/verify", {"answer": "Ты вчера говорил про отпуск.", "user": "tt", "rerank": False}); T("verify uncited claim", not v["ok"] and len(v["uncited"]) == 1)
v = P("/verify", {"answer": "Ты говорил про Омск [m:999999].", "user": "tt", "rerank": False}); T("verify missing id", v["cites"][0]["status"] == "missing")
oid = db("select id from s03_mem where user='owner' limit 1")
if oid:
    v = P("/verify", {"answer": "Ты говорил про это [m:%d]." % oid[0][0], "user": "tt", "rerank": False}); T("verify foreign (other user) blocked", v["cites"][0]["status"] == "foreign")
# 4 forgetting: young untouched, protected untouched, old low-score archived w/ sha, nothing deleted
now = time.time()
pr = P("/add_fact", {"fact": "Пользователь обещал маме звонить каждое воскресенье", "user": "ff", "ts": now - 90 * 86400})["id"]
va = P("/add_fact", {"fact": "Пользователь считает честность главным принципом", "user": "ff", "ts": now - 90 * 86400})["id"]
old = P("/add_fact", {"fact": "Пользователь однажды видел голубя возле магазина", "user": "ff", "ts": now - 90 * 86400, "prov": "thought"})["id"]
yg = P("/add_fact", {"fact": "Пользователь сегодня пил чай с мятой", "user": "ff"})["id"]
n1 = db("select count(*) from s03")[0][0]
d = P("/forget_pass", {"dry": True}); T("forget dry: no changes", d["archived"] >= 1 and db("select count(*) from s03_mem where archived=1")[0][0] == 0)
x = P("/forget_pass", {"apply": True, "dry": False}, 60)
arch = {r[0] for r in db("select id from s03_mem where archived=1")}
T("forget apply: old low archived", old in arch)
T("forget: promise/value protected", pr not in arch and va not in arch)
T("forget: young kept", yg not in arch)
T("forget: nothing deleted", db("select count(*) from s03")[0][0] == n1 and db("select text from s03 where id=?", (old,))[0][0] != "")
fr = db("select file,file_sha,sha from m10_archive where mem_id=?", (old,))[0]
T("archive file sha matches", hashlib.sha256(open(fr[0], "rb").read()).hexdigest() == fr[1] and any(json.loads(l)["sha"] == fr[2] for l in gzip.open(fr[0], "rt", encoding="utf-8")))
r = P("/recall", {"q": "голубь возле магазина", "user": "ff"}); T("archived excluded from recall", old not in (r.get("ids") or []))
# 5 forget scrubs archive + derived
P("/forget", {"user": "ff", "id": old}); 
T("forget scrubs archive copy", not any(json.loads(l)["id"] == old for l in gzip.open(fr[0], "rt", encoding="utf-8")) and db("select text from s03 where id=?", (old,))[0][0] == "")
T("s03 append-only intact", len(db("select name from sqlite_master where type='trigger' and name in ('s03_nodel','s03_noupd')")) == 2)
T("migration additive: row count only grew", db("select count(*) from s03")[0][0] >= n0)
print("TESTS pass=%d fail=%d" % (ST["ok"], ST["bad"]))
