#!/bin/bash
# stage3: шлюз :8082 (self_text только на вопросах о состоянии; строка хотфикса в FAST_SUFFIX) + бэкап БД памяти. Только процесс шлюза.
R=/root/nox/repo/nox-control; ML=$R/qs6/memory_layer.py; QC=$R/glm53/qs6_core.py; TS=$(date +%Y%m%d%H%M%S)
df -h /root | tail -1; ls -l /root/nox/memory/s03.db | awk '{print "s03.db bytes",$5}'
H="Accept: application/vnd.github.raw"; curl -fsSL -H "$H" "https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/web/restart.py?ref=main" -o /root/nox/hf_restart.py
for F in $ML $QC; do ls $F.bak_hotfix_* >/dev/null 2>&1 || cp -a $F $F.bak_hotfix_$TS; done
ML0=$(ls $ML.bak_hotfix_* | head -1); QC0=$(ls $QC.bak_hotfix_* | head -1)
python3 - <<P || exit 1
import sys
ml="$ML"; qc="$QC"
s=open(ml,encoding="utf-8").read()
if "NOXHF" not in s:
    a="self_text=self.self_text(),"
    assert a in s, "ml anchor"
    s=s.replace(a,'self_text=(self.self_text() if __import__("re").search(r"сервер|gpu|видеокарт|состояни|статус|телеметр|нагрузк|ток/с|скорост|модел|верси|сборк|порт|где ты|на чём|на чем|что с тобой|как ты работаешь|журнал|истори|диск", user_text or "", __import__("re").I) else ""),  # NOXHF: блок о себе только на вопросах о состоянии',1)
    open(ml,"w",encoding="utf-8").write(s); print("ml patched")
q=open(qc,encoding="utf-8").read()
if "NOXHF" not in q:
    import re
    m=re.search(r'^FAST_SUFFIX = (.*)$',q,re.M); assert m, "qc anchor"
    line=m.group(1); assert line.rstrip().endswith('"') and "#" not in line, "unexpected FAST_SUFFIX: "+line[:60]
    q=q[:m.start()]+'FAST_SUFFIX = '+line.rstrip()[:-1]+' Никогда не пересказывай блок внутреннего состояния и телеметрию, если Создатель прямо не спросил о состоянии/сервере. На приветствие — 1–3 живые фразы. Не предлагай списков «Что хочешь: →…»."  # NOXHF'+q[m.end():]
    open(qc,"w",encoding="utf-8").write(q); print("qc patched")
P
python3 -I -m py_compile $ML $QC || { echo compile fail; cp -a $ML0 $ML; cp -a $QC0 $QC; exit 1; }
cat > /root/nox/hotfix_gw_rollback.sh <<R
#!/bin/bash
cp -a $ML0 $ML; cp -a $QC0 $QC
python3 /root/nox/hf_restart.py 8082 /root/nox/logs/gateway.log; sleep 5; curl -s -m5 -o /dev/null -w "gw %{http_code}\n" http://127.0.0.1:8082/health
R
chmod +x /root/nox/hotfix_gw_rollback.sh
python3 /root/nox/hf_restart.py 8082 /root/nox/logs/gateway.log; sleep 8
ask(){ curl -sN -m90 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}],\"stream\":true,\"nox_mode\":\"fast\"}" | python3 -c "
import sys,json
t=''
for l in sys.stdin:
    try: o=json.loads(l)
    except Exception: continue
    t+=(o.get('message') or {}).get('content','')
    if o.get('error'): t+='[ERR '+str(o['error'])[:80]+']'
print(repr(t[:300]))"; }
r=$(ask "привет"); echo "after gw restart: $r"
if [ -z "$r" ] || [ "$r" = "''" ] || echo "$r" | grep -q "ERR"; then echo ROLLBACK; bash /root/nox/hotfix_gw_rollback.sh; exit 1; fi
echo "rollback: bash /root/nox/hotfix_gw_rollback.sh"
echo "== db schema (code only)"; python3 - <<'P'
import sqlite3
c=sqlite3.connect('file:/root/nox/memory/s03.db?mode=ro',uri=True)
for n,t,s in c.execute("select name,type,substr(sql,1,230) from sqlite_master where name like '%episod%' or name like 'mem_fts%' or type='trigger'"): print(t,n,(s or '').replace('\n',' '))
P
free=$(df --output=avail -B1 /root | tail -1); sz=$(stat -c %s /root/nox/memory/s03.db); echo "free=$free size=$sz"
if [ $free -gt $((sz*2+1000000000)) ]; then cp -a /root/nox/memory/s03.db /root/nox/memory/s03.db.bak_hotfix_$TS && echo "db backup cp ok"; else echo "no space for cp"; fi
