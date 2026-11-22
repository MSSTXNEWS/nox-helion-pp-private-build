import sqlite3, time
c=sqlite3.connect("/root/nox/memory/s03.db")
for t in ("episodes","facts"):
    try:
        cols=[r[1] for r in c.execute("pragma table_info(%s)"%t)]; print(t, cols[:10])
        tc=[x for x in cols if x in ("ts","created","created_at","t")]
        if tc: print(" last:", c.execute("select max(%s), count(*) from %s"%(tc[0],t)).fetchone(), "now", time.time())
        txt=[x for x in cols if x in ("text","content","body")]
        if txt and tc: print(" recent:", [r[0][:60] for r in c.execute("select %s from %s order by %s desc limit 3"%(txt[0],t,tc[0]))])
    except Exception as e: print(t,"ERR",e)
