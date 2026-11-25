N=/workspace/nox
$N/venv/bin/python - <<'PY'
import sys,time,os; sys.path.insert(0,"/workspace/nox/stewards"); import nox_orch as O
d=O.N+"/state/web/web_conv"; now=time.time()
fr=[(round(now-os.path.getmtime(d+"/"+f)),f) for f in os.listdir(d) if f.endswith(".json") and now-os.path.getmtime(d+"/"+f)<900]
print("fresh convs:",sorted(fr)[:8]); print("non-probe fresh:",[f for a,f in fr if not O.is_probe(f[:-5])])
for i in range(5):
    print("raw",O._raw_chat(),"live",O.chat_active(use_hold=False)); time.sleep(3)
PY
ss -Htnp state established '( dport = :8090 or dport = :8084 )' | grep -o 'users:(("[^"]*",pid=[0-9]*' | sort | uniq -c
