import sqlite3, json
esc=[json.dumps("Тортилла-7")[1:-1], json.dumps("Тромсё")[1:-1]]
c=sqlite3.connect("/root/nox/memory/s03.db")
for (t,) in c.execute("select name from sqlite_master where type='table'"):
    for r in c.execute("pragma table_info('%s')"%t).fetchall():
        col=r[1]
        for pat in ["Тортилла","Тромс","Tortilla"]+esc:
            try: n=c.execute("select count(*) from '%s' where cast(\"%s\" as text) like ?"%(t,col),("%"+pat+"%",)).fetchone()[0]
            except Exception: n=0
            if n: print("DB",t,col,pat[:12],n)
for f in ["/root/nox/state/core_conv_default.json","/root/nox/state/predictive_self.json"]:
    d=json.load(open(f)); print(f, type(d).__name__, list(d)[:8] if isinstance(d,dict) else len(d))
    s=json.dumps(d,ensure_ascii=False); i=s.find("Тортилла"); print("  ctx:", s[max(0,i-200):i+80].replace("\n"," "))
