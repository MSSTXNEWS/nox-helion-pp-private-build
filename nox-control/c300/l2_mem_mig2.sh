echo "K1: l2_mem_mig2"
python3 - <<'PY'
import sqlite3,json,urllib.request as ur
def P(u,o):
    rq=ur.Request("http://127.0.0.1:"+u,data=json.dumps(o).encode(),headers={"Content-Type":"application/json"}); return json.loads(ur.urlopen(rq,timeout=30).read())
c=sqlite3.connect("/workspace/nox/state/living/mem.db")
rows=c.execute("select text,sensitive from mem").fetchall()
ok=sk=dup=0
for t,s in rows:
    if s: sk+=1; continue
    r=P("18220/add_fact",{"fact":t,"user":"owner","cid":"migrated"}).get("id")
    if r and r>0: ok+=1
    else: dup+=1
print("old_total",len(rows),"migrated",ok,"skipped_sensitive",sk,"dup_or_short",dup)
db=sqlite3.connect("/workspace/nox/state/core/s03.db")
print("s03 by user:",db.execute("select user,status,count(*) from s03_mem group by 1,2").fetchall())
PY
