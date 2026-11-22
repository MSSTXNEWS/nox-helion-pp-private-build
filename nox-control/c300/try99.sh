#!/bin/bash
cat > /root/nox/flash_try.sh <<'S'
#!/bin/bash
# ждём текущий замер ngl24, потом пробуем ngl99 -c 8192 -ub 256; при сбое — назад
for i in $(seq 60); do grep -q "^pp" /root/nox/logs/flash_ab.log && break; sleep 5; done
cp /root/nox/logs/flash_ab.log /root/nox/logs/flash_ab_24.log
sed 's/-ngl 24/-ngl 99/; s/-c 16384/-c 8192/; s/-ub 512/-ub 256/' /root/nox/start_glm.sh.ngl24 > /root/nox/start_glm.sh
bash /root/nox/start_glm.sh
for i in $(seq 60); do sleep 5; curl -sf -m 2 127.0.0.1:8081/health >/dev/null && break; pgrep -f 'port 8081' >/dev/null || break; done
if curl -sf -m 2 127.0.0.1:8081/health >/dev/null; then
  python3 - > /root/nox/logs/flash_ab_99.log 2>&1 <<'P'
import json,urllib.request,time
txt=open("/root/nox/canon_v5.txt",encoding="utf-8").read()[:2500]
b={"prompt":"Кратко перескажи:\n"+txt+"\nПересказ:","n_predict":80,"cache_prompt":False}
r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/completion",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=1800))
tm=r["timings"];print("ngl99 pp %.2f tg %.2f"%(tm["prompt_per_second"],tm["predicted_per_second"]))
P
  python3 - <<'P'
import re
a=open("/root/nox/logs/flash_ab_24.log").read(); b=open("/root/nox/logs/flash_ab_99.log").read()
tg24=float(re.search(r"tg ([\d.]+)",a).group(1)); m=re.search(r"tg ([\d.]+)",b); tg99=float(m.group(1)) if m else 0
open("/root/nox/logs/flash_pick.log","w").write("tg24=%s tg99=%s\n"%(tg24,tg99))
if tg99 < tg24*1.05:
    import shutil,subprocess; shutil.copy("/root/nox/start_glm.sh.ngl24","/root/nox/start_glm.sh"); subprocess.run("bash /root/nox/start_glm.sh",shell=True)
    open("/root/nox/logs/flash_pick.log","a").write("keep ngl24\n")
else: open("/root/nox/logs/flash_pick.log","a").write("keep ngl99\n")
P
else
  echo "ngl99 c8192 failed" > /root/nox/logs/flash_pick.log; cp /root/nox/start_glm.sh.ngl24 /root/nox/start_glm.sh; bash /root/nox/start_glm.sh
fi
pgrep -f glm_watch.sh >/dev/null || (nohup setsid bash /root/nox/glm_watch.sh >/dev/null 2>&1 </dev/null &)
echo done >> /root/nox/logs/flash_pick.log
S
nohup setsid bash /root/nox/flash_try.sh >/dev/null 2>&1 < /dev/null &
echo started
