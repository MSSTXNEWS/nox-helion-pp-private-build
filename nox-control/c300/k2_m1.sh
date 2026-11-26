echo "C300: k2_m1"
N=/workspace/nox; K=$N/secrets/meili_key.txt; SE=$N/svc/start_extra.sh
umask 077
cp -p $K $K.bak_k2 2>/dev/null; chmod 600 $K.bak_k2; cp -p $SE $SE.bak_k2
openssl rand -hex 32 > $K.new && chmod 600 $K.new
python3 - <<'P'
import re
f="/workspace/nox/svc/start_extra.sh"; L=open(f).read().split("\n"); n=0
for i,l in enumerate(L):
    if "svc/meili/meilisearch" in l and "--master-key" in l:
        l2=re.sub(r'--master-key "\$\(cat [^)]+\)" ?','',l)
        l2=l2.replace('nohup setsid /workspace/nox/svc/meili/meilisearch','MEILI_MASTER_KEY="$(cat /workspace/nox/secrets/meili_key.txt)" nohup setsid /workspace/nox/svc/meili/meilisearch',1)
        L[i]=l2; n+=1
open(f,"w").write("\n".join(L)); print("start_extra lines patched:",n,"| master-key flag left:", any("--master-key" in x for x in L))
P
cat > /tmp/k2_mt.py <<'P'
import urllib.request,sys
def code(key,path="/indexes/nox"):
    rq=urllib.request.Request("http://127.0.0.1:7700"+path,headers={"Authorization":"Bearer "+key})
    try: return urllib.request.urlopen(rq,timeout=15).status
    except urllib.error.HTTPError as e: return e.code
    except Exception as e: return "err"
old=open(sys.argv[1]).read().strip(); new=open(sys.argv[2]).read().strip()
print("old key:",code(old),"| new key:",code(new))
P
echo "--- before (old file vs new candidate)"; python3 /tmp/k2_mt.py $K.bak_k2 $K.new
echo "--- docs before: $(python3 - <<'P'
import urllib.request,json
k=open('/workspace/nox/secrets/meili_key.txt').read().strip()
rq=urllib.request.Request("http://127.0.0.1:7700/indexes/nox/stats",headers={"Authorization":"Bearer "+k})
print(json.load(urllib.request.urlopen(rq,timeout=15)).get("numberOfDocuments"))
P
)"
mv $K.new $K
P=$(ss -ltnp | grep ':7700 ' | grep -o 'pid=[0-9]*' | cut -d= -f2); kill $P; for i in $(seq 30); do kill -0 $P 2>/dev/null || break; sleep 1; done
cd $N/svc && MEILI_MASTER_KEY="$(cat $K)" RUNNER_TRACKING_ID=k2m setsid -f nohup $N/svc/meili/meilisearch --http-addr 127.0.0.1:7700 --db-path $N/svc/data/meili --no-analytics --env production >> $N/svc/logs/meili.log 2>&1 < /dev/null
for i in $(seq 30); do (echo > /dev/tcp/127.0.0.1/7700) 2>/dev/null && break; sleep 1; done; sleep 3
echo "--- after restart"; python3 /tmp/k2_mt.py $K.bak_k2 $K
NEWPID=$(ss -ltnp | grep ':7700 ' | grep -o 'pid=[0-9]*' | cut -d= -f2); echo "cmdline has master-key flag: $(tr '\0' ' ' < /proc/$NEWPID/cmdline | grep -c -- '--master-key')"
RES=$(python3 /tmp/k2_mt.py $K.bak_k2 $K)
case "$RES" in *"old key: 401 | new key: 200"*) echo "OK";; *) echo "FAIL -> rollback"; cp -p $K.bak_k2 $K; cp -p $SE.bak_k2 $SE; kill $NEWPID; sleep 2; cd $N/svc && MEILI_MASTER_KEY="$(cat $K)" RUNNER_TRACKING_ID=k2m setsid -f nohup $N/svc/meili/meilisearch --http-addr 127.0.0.1:7700 --db-path $N/svc/data/meili --no-analytics --env production >> $N/svc/logs/meili.log 2>&1 < /dev/null; exit;; esac
echo "--- clients reading key file (names only)"
grep -rIl "meili_key" $N --include=*.py --include=*.sh --include=*.js --include=*.json --include=*.yaml --include=*.yml --include=*.conf --include=*.env 2>/dev/null | grep -v -E "venv|node_modules|\.bak|/logs?/|k2_|/backups?/" | head -30
echo "--- files with hardcoded old key (names only)"
OLD=$(cat $K.bak_k2); timeout 100 grep -rIlF -- "$OLD" $N/svc $N/web $N/ops $N/agent $N/stewards $N/brain $N/integration $N/state/*.json /etc/supervisor 2>/dev/null | grep -v -E "\.bak|/logs?/|\.log$|node_modules|k2_" | head -20
echo "--- reindex"; $N/venv/bin/python $N/svc/nox_index.py 2>&1 | tail -1 | cut -c1-80
echo "docs after: $(python3 - <<'P'
import urllib.request,json
k=open('/workspace/nox/secrets/meili_key.txt').read().strip()
rq=urllib.request.Request("http://127.0.0.1:7700/indexes/nox/stats",headers={"Authorization":"Bearer "+k})
print(json.load(urllib.request.urlopen(rq,timeout=15)).get("numberOfDocuments"))
P
)"
ls -la $K | cut -c1-10
