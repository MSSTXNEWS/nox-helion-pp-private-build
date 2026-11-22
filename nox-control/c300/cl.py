import sqlite3, shutil, time
db="/root/nox/memory/s03.db"; shutil.copy(db, db+".bak_test_"+time.strftime("%H%M%S"))
c=sqlite3.connect(db); tot=0
for (t,) in c.execute("select name from sqlite_master where type='table'").fetchall():
    cols=[r[1] for r in c.execute("pragma table_info('%s')"%t) if (r[2] or "").upper() in ("TEXT","")]
    for col in cols:
        try:
            n=c.execute("select count(*) from '%s' where \"%s\" like '%%Тортилла-7%%' or \"%s\" like '%%Тромсё%%'"%(t,col,col)).fetchone()[0]
        except Exception: continue
        if n:
            print(t,col,n)
            if t.endswith(("_fts","_data","_idx","_content","_docsize","_config")): continue
            c.execute("delete from '%s' where \"%s\" like '%%Тортилла-7%%' or \"%s\" like '%%Тромсё%%'"%(t,col,col)); tot+=n
c.commit(); print("deleted rows", tot)
p="/root/nox/logs/chat_turns.jsonl"
L=open(p,encoding="utf-8").read().split("\n"); K=[l for l in L if "Тортилла-7" not in l and "Тромсё" not in l]; open(p,"w",encoding="utf-8").write("\n".join(K)); print("turns removed", len(L)-len(K))
