#!/bin/bash
# Замена главной модели GLM-5.3 -> GLM-5.3-Flash (решение Создателя 22.11). Этапы по аргументу.
S="$1"; LG=/root/nox/logs; MF=/root/nox/models/manifests; mkdir -p $LG $MF
case "$S" in
swap0)
  echo "== baseline + манифест"
  python3 - <<'P'
import json,os,glob,subprocess,urllib.request,time
bl={"ts":time.strftime("%F %T"),"model":"GLM-5.3-UD-Q4_K_XL","baseline":{"tg_tok_s":1.2,"pp_tok_s":2.7,"args":open("/root/nox/gpu_tier/glm.args").read().strip() if os.path.exists("/root/nox/gpu_tier/glm.args") else "-c 16384 -ngl 24 -ot exps=CPU -t 24 -tb 24 -fa on --parallel 1 -b 512 -ub 256 --jinja","note":"llama.cpp, 4B на :8083"}}
files=[]
for d in ("/dev/shm/nox_glm","/root/nox/glm53_disk"):
    for f in sorted(glob.glob(d+"/*.gguf")): files.append({"name":os.path.basename(f),"size":os.path.getsize(f),"where":d})
api=json.load(urllib.request.urlopen("https://huggingface.co/api/models/unsloth/GLM-5.3-GGUF/tree/main/UD-Q4_K_XL",timeout=30)) if True else []
hf={os.path.basename(x["path"]):{"size":x.get("size"),"sha256":(x.get("lfs") or {}).get("oid")} for x in api}
for f in files: f["hf"]=hf.get(f["name"])
man={"hf_repo":"unsloth/GLM-5.3-GGUF","subdir":"UD-Q4_K_XL","shards":files,"hf_listing_count":len(hf),"glm_args":bl["baseline"]["args"],"launch":"llama-server -m <shard1> --host 127.0.0.1 --port 8081 $GLM_ARGS (mmap, KV f16)","note":"Веса не хранятся (решение Создателя), только манифест для повторного скачивания"}
json.dump(man,open("/root/nox/models/manifests/glm53_ud_q4kxl.json","w"),ensure_ascii=False,indent=1)
json.dump(bl,open("/root/nox/logs/MODEL_SWAP.json","w"),ensure_ascii=False,indent=1)
print("shards",len(files),"with_hf_sha",sum(1 for f in files if f["hf"] and f["hf"]["sha256"]),"hf_listing",len(hf))
print([ (f["name"][-18:],f["size"]) for f in files][:12])
P
  python3 -c "import json;m=json.load(open('/root/nox/models/manifests/glm53_ud_q4kxl.json'));print('manifest ok',len(m['shards']))"
  echo "== кандидаты Flash на HF"
  for q in "GLM-5.3-Flash" "GLM-5.3-Flash-GGUF"; do curl -s -m20 "https://huggingface.co/api/models?search=$q&limit=15" | python3 -c 'import sys,json;[print(x["id"],x.get("downloads"),x.get("tags",[])[:3]) for x in json.load(sys.stdin)]'; done
  ;;
swap1a)
  echo "== кто держит/перезапускает :8081"
  for p in $(pgrep -f "llama-server.*8081"); do echo "pid $p ppid $(ps -o ppid= -p $p) $(tr '\0' ' ' < /proc/$p/cmdline | cut -c1-120)"; ps -o pid,ppid,etime,cmd -p $(ps -o ppid= -p $p) | cut -c1-160; done
  pgrep -af "watchdog|monitor|redo_worker|glm_|sweep|supervis|services" | grep -v pgrep | cut -c1-150
  echo "== где упомянут 8081/glm_start в автозапуске"
  grep -rlE "8081|glm_start|ik_llama" /etc/cron.d /root/nox/services.d /root/nox/scripts/lib /root/nox/boot_s1.sh /root/nox/gpu_tier /etc/supervisor* 2>/dev/null | head -12
  crontab -l 2>/dev/null | head -5; ls /root/nox/services.d | head
  echo "== манифест"; python3 -c "import json;m=json.load(open('/root/nox/models/manifests/glm53_ud_q4kxl.json'));print(len(m['shards']),sum(1 for s in m['shards'] if s.get('hf') and s['hf'].get('sha256')),'sha');print([s['name'][-14:] for s in m['shards']])"
  wc -c /root/nox/models/manifests/glm53_ud_q4kxl.json /root/nox/logs/MODEL_SWAP.json
  df -h /dev/shm /root | cat
  ;;
swapA)
  echo "== A: стоп GLM + манифест + размер/лицензия Flash (удалений нет)"
  pkill -f "/root/nox/exp_driver_B.py"; pkill -f "/root/nox/glm_watch.sh"; sleep 1
  for p in $(pgrep -f "llama-server.*--port 8081"); do kill -TERM $p; done
  for i in $(seq 1 24); do pgrep -f "llama-server.*--port 8081" >/dev/null || break; sleep 5; done
  pgrep -af "llama-server|exp_driver|glm_watch" | cut -c1-110; curl -s -m3 -o /dev/null -w "8081=%{http_code}\n" localhost:8081/health; curl -s -m3 -o /dev/null -w "8083=%{http_code}\n" localhost:8083/health
  mkdir -p /root/nox/state/MODEL_SWAP; D=/root/nox/state/MODEL_SWAP
  GD=/dev/shm/nox_glm; ls -l --block-size=1 $GD/*.gguf /root/nox/glm53_disk/*.gguf > $D/glm53_manifest.txt 2>&1
  python3 - <<'P'
import json,urllib.request
m=json.load(open("/root/nox/models/manifests/glm53_ud_q4kxl.json"))
info=json.load(urllib.request.urlopen("https://huggingface.co/api/models/unsloth/GLM-5.3-GGUF",timeout=30))
with open("/root/nox/state/MODEL_SWAP/glm53_manifest.txt","a") as f:
    f.write("\nHF repo: unsloth/GLM-5.3-GGUF revision: %s\n"%info.get("sha"))
    for s in m["shards"]:
        f.write("%s %s sha256=%s where=%s\n"%(s["name"],s["size"],(s.get("hf") or {}).get("sha256"),s["where"]))
print("manifest lines",sum(1 for _ in open("/root/nox/state/MODEL_SWAP/glm53_manifest.txt")),"rev",info.get("sha"))
for r in ("unsloth/GLM-5.3-Flash-GGUF","ggml-org/GLM-5.3-Flash-GGUF"):
    try:
        i=json.load(urllib.request.urlopen("https://huggingface.co/api/models/"+r,timeout=30)); print("==",r,"license:",(i.get("cardData") or {}).get("license"),"rev",i.get("sha"))
        tot=0
        for sub in ("","UD-Q4_K_XL"):
            u="https://huggingface.co/api/models/%s/tree/main%s"%(r,("/"+sub) if sub else "")
            try: tr=json.load(urllib.request.urlopen(u,timeout=30))
            except Exception as e: continue
            for x in tr:
                n=x["path"]
                if x["type"]=="file" and (("Q4_K_XL" in n) or ("mmproj" in n.lower()) or ("Q4_K_M" in n)) and n.endswith(".gguf"):
                    print(n,x.get("size")); 
                if x["type"]=="directory": print("dir",n)
    except Exception as e: print(r,"err",e)
P
  df -h /dev/shm | tail -1
  ;;
swapB)
  echo "== B: поиск скриптов эталона, кто занял shm, кто собирает движок"
  find / -xdev \( -name mind_bench.py -o -name soul_recognition.py -o -name ru_probe* -o -name "fid*prov*" \) -not -path "*/node_modules/*" 2>/dev/null | head -10
  ls -d /root/nox/MIND /root/nox/GROW /root/nox/src/wow7/* /tmp/nox_v7 2>/dev/null | head -12
  du -sh /dev/shm/* 2>/dev/null | sort -rh | head -8; df -h /dev/shm | tail -1
  pgrep -af "cmake|gmake|git clone|curl.*huggingface|hf_|aria2|python3 /root/nox" | grep -v pgrep | cut -c1-170 | head -12
  ls -la /root/nox | grep -E "llama.cpp-f|flash" ; ls /root/nox/state/MODEL_SWAP 2>/dev/null
  cat /root/nox/gpu_tier/glm.args; uptime
  ;;
swapC)
  echo "== C: ТОЛЬКО ЧТЕНИЕ. инвентарь истории ответов GLM-5.3 (счётчики, без текста)"
  python3 - <<'P'
import json,glob,os,sqlite3,collections
def cnt_jsonl(f):
    n=0;keys=collections.Counter();models=collections.Counter()
    for l in open(f,errors="replace"):
        try:d=json.loads(l)
        except Exception:continue
        n+=1
        if isinstance(d,dict):
            keys.update(d.keys())
            for k in("model","upstream","tier","nox_mode","mode"):
                if k in d:models[str(d[k])[:30]]+=1
    return n,dict(keys.most_common(12)),dict(models.most_common(6))
for f in sorted(glob.glob("/root/nox/logs/*.jsonl"))+sorted(glob.glob("/root/nox/events/*.jsonl"))+sorted(glob.glob("/root/nox/memory/*.jsonl")):
    try:print(f,os.path.getsize(f),cnt_jsonl(f))
    except Exception as e:print(f,"err",e)
db="/root/nox/memory/s03.db"
c=sqlite3.connect("file:%s?mode=ro"%db,uri=True)
for (n,) in c.execute("select name from sqlite_master where type='table'"):
    try:
        k=c.execute("select count(*) from %s"%n).fetchone()[0]
        cols=[r[1] for r in c.execute("pragma table_info(%s)"%n)]
        print("tbl",n,k,cols[:10])
    except Exception as e:print("tbl",n,"err")
P
  ls /root/nox/receipts | head -3; ls /root/nox/receipts | wc -l
  ls /root/nox/memory | head -12; ls -la /root/nox/logs | grep -iE "chat|life|trace|turn|journal" | cut -c1-120
  find /root/nox -maxdepth 3 -iname "*life_journal*" -o -maxdepth 3 -iname "*trace*" 2>/dev/null | head -8
  ;;
swapD)
  echo "== D: ТОЛЬКО ЧТЕНИЕ. состояние замены"
  date +%T; pgrep -af "llama-server|flash.py|cmake|curl.*gguf|exp_driver" | grep -v pgrep | cut -c1-110 | head -5
  for p in 8081 8082 8083 8091; do echo -n "$p="; curl -s -m4 -o /dev/null -w "%{http_code} " http://127.0.0.1:$p/health; done; echo
  df -h /dev/shm /root | awk 'NR>1{print $6,$3,$4}'; free -g | sed -n 2p | awk '{print "RAM used",$3,"free",$4}'
  ls /root/nox/state/MODEL_SWAP/ 2>/dev/null | tr '\n' ' '; echo
  tail -n 3 /root/nox/logs/glm_8081.log 2>/dev/null | cut -c1-160
  grep -E "verdict|вердикт|PASS|FAIL" /root/nox/state/MODEL_SWAP.json 2>/dev/null | head -3 | cut -c1-160
  tail -n 2 /root/nox/logs/flash.log | cut -c1-120
  ;;
swapE)
  echo "== E: диагностика шлюза и Flash"
  pgrep -af "llama-server|gateway|uvicorn" | grep -v pgrep | cut -c1-420
  grep -n "FLASH FAILED" -B3 -A3 /root/nox/logs/flash.log | cut -c1-200 | tail -14
  tail -n 4 /root/nox/logs/flash.log | cut -c1-200
  curl -s -m5 localhost:8082/health | head -c 300; echo
  curl -s -m20 localhost:8082/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"nox_mode":"fast","max_tokens":20}' | head -c 300; echo
  G=$(ls /root/nox/repo/nox-control/glm53/gateway.py /root/nox/nox-control/glm53/gateway.py 2>/dev/null | head -1); echo "gw=$G"
  grep -nE "8081|8083|UPSTREAM|GLM-5|glm53|timeout|MODEL" $G | cut -c1-170 | head -40
  pgrep -f "gateway.py" | head -1 | xargs -I{} sh -c 'tr "\0" "\n" < /proc/{}/environ | grep -E "NOX_|UPSTREAM|GLM" | cut -c1-120; ls -l /proc/{}/cwd'
  ls /root/nox/logs | grep -iE "gateway|gw|8082" ; tail -n 12 /root/nox/logs/gateway.log 2>/dev/null | cut -c1-220
  ls /root/nox/glm53_disk | head; ls /root/nox/state/MODEL_SWAP
  ;;
*) echo "unknown stage $S";;
esac
