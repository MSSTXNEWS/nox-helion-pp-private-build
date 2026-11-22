import shutil, time, subprocess, re
Q="/root/nox/repo/nox-control/"; ts=time.strftime("%H%M%S")
shutil.copy("/tmp/mem_filter.py", Q+"qs6/mem_filter.py")
# 1) deep: фильтр фактов
p="/root/nox/web_server.py"; s=open(p).read(); shutil.copy(p,p+".bak_mf_"+ts)
old='_facts = [str(x) for x in ((_prep or {}).get("facts") or []) if str(x).strip()]'
new='from qs6.mem_filter import clean as _mclean; _facts = _mclean((_prep or {}).get("facts") or [], limit=4)'
print("deep", s.count(old)); s=s.replace(old,new); open(p,"w").write(s)
print("web compile", subprocess.run(["python3","-m","py_compile",p]).returncode)
# 2) шлюз/Prime: фильтр recall
g=Q+"glm53/gateway_prime.py"; t=open(g).read(); shutil.copy(g,g+".bak_mf_"+ts)
o2='return {"core": r["core"]["text"], "recalled": [h["text"] for h in r["search"]["hits"]]}'
n2='from qs6.mem_filter import clean as _mc, clean_text as _mct; return {"core": _mct(r["core"]["text"]), "recalled": _mc([h["text"] for h in r["search"]["hits"]], limit=5)}'
print("prime", t.count(o2)); t=t.replace(o2,n2); open(g,"w").write(t)
print("prime compile", subprocess.run(["python3","-m","py_compile",g]).returncode)
