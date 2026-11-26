echo "C300: k2_a3"
N=/workspace/nox; ST=$N/state
D=$N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF; F=$D/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf
pkill -f "k2dl|Thinking-2507-Q4_K_M.gguf" ; sleep 2
S=$(stat -c %s $F); echo "partial=$S"
cat > $ST/k2_dl.py <<'P'
import os,sys,json,time,threading,urllib.request
URL="https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF/resolve/main/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf"
F=sys.argv[1]; TOTAL=18556686752; BLK=64<<20; TH=6
PG=F+".k2prog"
done=set(json.load(open(PG))) if os.path.exists(PG) else set()
have=os.path.getsize(F) if os.path.exists(F) else 0
fd=os.open(F,os.O_RDWR|os.O_CREAT)
if os.fstat(fd).st_size<TOTAL: os.ftruncate(fd,TOTAL)
nb=(TOTAL+BLK-1)//BLK
if not done: done={i for i in range(nb) if (i+1)*BLK<=have-BLK}  # доверяем префиксу, кроме последнего блока
todo=[i for i in range(nb) if i not in done]; lock=threading.Lock(); t0=time.time()
log=open(os.path.dirname(F)+"/../../../state/k2_dl.log","a")
def worker():
    while True:
        with lock:
            if not todo: return
            i=todo.pop(0)
        a=i*BLK; b=min(TOTAL,a+BLK)-1
        for k in range(12):
            try:
                rq=urllib.request.Request(URL,headers={"Range":"bytes=%d-%d"%(a,b)})
                d=urllib.request.urlopen(rq,timeout=60).read()
                if len(d)!=b-a+1: raise Exception("short")
                os.pwrite(fd,d,a)
                with lock:
                    done.add(i); json.dump(sorted(done),open(PG,"w"))
                    if len(done)%10==0: print("%.1f%% %ds"%(100*len(done)/nb,time.time()-t0),file=log,flush=True)
                break
            except Exception as e: time.sleep(5+k*3)
ts=[threading.Thread(target=worker) for _ in range(TH)]
[t.start() for t in ts]; [t.join() for t in ts]
ok=len(done)==nb; print("FINISHED ok=%s done=%d/%d"%(ok,len(done),nb),file=log,flush=True)
P
env RUNNER_TRACKING_ID=k2dl2 setsid -f nice -n 10 ionice -c2 -n7 python3 $ST/k2_dl.py $F </dev/null >>$ST/k2_dl.err 2>&1
sleep 40; tail -2 $ST/k2_dl.log; cat $ST/k2_dl.err | tail -3; cat $ST/k2_restart.log | tail -3
python3 -c "import json;print(len(json.load(open('$F.k2prog'))),'blocks of 277')"
