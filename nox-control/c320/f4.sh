#!/bin/bash
# kill my own stray recon 'strings' procs only
pkill -f 'strings -n 8 /dev/shm/glm53f' ; sleep 1
mkdir -p /root/nox/state/flash_bench /root/nox/backup
[ -f /root/nox/backup/start_glm.sh.orig_flashopt ] || cp -a /root/nox/start_glm.sh /root/nox/backup/start_glm.sh.orig_flashopt
cat > /root/nox/flash_bench.py <<'PY'
import json,sys,time,urllib.request,threading
URL='http://127.0.0.1:8081/completion'
def post(p,n):
    d={'prompt':p,'n_predict':n,'temperature':0,'top_k':1,'cache_prompt':False,'seed':1}
    r=urllib.request.Request(URL,json.dumps(d).encode(),{'Content-Type':'application/json'})
    t=time.time(); o=json.load(urllib.request.urlopen(r,timeout=900)); o['wall']=time.time()-t; return o
def s(o):
    t=o['timings']; return dict(pp=round(t['prompt_per_second'],2),tg=round(t['predicted_per_second'],2),pn=t['prompt_n'],gn=t['predicted_n'],ttft=round(t['prompt_ms']/1000,2),dn=t.get('draft_n'),da=t.get('draft_n_accepted'))
short="Объясни своими словами, чем модель Mixture-of-Experts отличается от плотной модели, и почему она быстрее на процессоре."
body=' '.join("Факт %d: узел %d соединён с узлом %d, значение %d, метка %s."%(i,i*7%101,i*13%97,i*i%1009,'abcdefgh'[i%8]) for i in range(int(sys.argv[2]) if len(sys.argv)>2 else 105))
long_p=body+"\nВопрос: чему равно значение в Факте 50 и какая у него метка? Ответь коротко."
R={'name':sys.argv[1]}
r=post(short,96); R['short']=s(r); R['short_text']=r['content'][:300]
r=post(long_p,48); R['long']=s(r); R['long_text']=r['content'][:200]
res=[]
def w(i): res.append(post("Расскажи подробно про тему номер %d: %s"%(i,['сети','память','звёзды','музыка'][i]),64))
th=[threading.Thread(target=w,args=(i,)) for i in range(4)]; t=time.time()
[x.start() for x in th]; [x.join() for x in th]; wall=time.time()-t
R['par4']=dict(agg_tg=round(sum(o['timings']['predicted_n'] for o in res)/wall,2),per_slot=[round(o['timings']['predicted_per_second'],2) for o in res],wall=round(wall,1))
print(json.dumps(R,ensure_ascii=False))
PY
cat > /root/nox/flash_bench.sh <<'SH'
#!/bin/bash
# usage: flash_bench.sh NAME "FLAGS" [CPUSET] ; background-safe; result -> /root/nox/state/flash_bench/NAME.json
N=$1; F=$2; C=${3:-0-17}; O=/root/nox/state/flash_bench; BIN=/root/nox/llama.cpp-f/build/bin/llama-server
M=/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf
exec 9>/tmp/flash_bench.lock; flock 9
for p in $(pgrep -f 'llama-server.*--port 8081'); do kill $p; done
for i in $(seq 60); do pgrep -f 'llama-server.*--port 8081' >/dev/null || break; sleep 1; done
echo "$F | cpus=$C" > $O/$N.cfg
GGML_CUDA_NO_PINNED=1 nohup nice -n 19 taskset -c $C $BIN -m $M --host 127.0.0.1 --port 8081 $F > $O/$N.srv.log 2>&1 &
ok=0; for i in $(seq 240); do curl -sf localhost:8081/health >/dev/null && { ok=1; break; }; sleep 2; done
if [ $ok = 1 ]; then python3 /root/nox/flash_bench.py $N > $O/$N.json 2>$O/$N.err; else echo '{"name":"'$N'","error":"no_health"}' > $O/$N.json; fi
echo done > $O/$N.done
SH
chmod +x /root/nox/flash_bench.sh
BASE="--parallel 4 -c 32768 -fa on --jinja -ngl 24 -ot exps=CPU --reasoning off --no-op-offload -t 18 -tb 18 -ub 512 -b 2048"
echo "$BASE" > /root/nox/state/flash_bench/BASE.flags
rm -f /root/nox/state/flash_bench/base0.done
nohup /root/nox/flash_bench.sh base0 "$BASE" 0-17 >/dev/null 2>&1 &
sleep 2; pgrep -af strings | wc -l; echo started
