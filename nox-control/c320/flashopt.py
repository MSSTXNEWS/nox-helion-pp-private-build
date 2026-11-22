import json,os,sys,time,subprocess,signal,random,threading,urllib.request,atexit
O='/root/nox/state/flash_bench'; BIN='/root/nox/llama.cpp-f/build/bin/llama-server'
M='/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf'
URL='http://127.0.0.1:8081'
ST={'stages':{}}; LOGF=open(O+'/driver.log','a')
def log(*a):
    LOGF.write(time.strftime('%H:%M:%S ')+' '.join(map(str,a))+'\n'); LOGF.flush()
def save(): json.dump(ST,open(O+'/FLASH_OPT.json','w'),ensure_ascii=False,indent=1)
def sh(c): return subprocess.run(c,shell=True,capture_output=True,text=True).stdout
def pids(pat):
    out=[]
    for d in os.listdir('/proc'):
        if d.isdigit() and int(d)!=os.getpid():
            try: c=open('/proc/%s/cmdline'%d).read().replace('\0',' ')
            except Exception: continue
            if pat in c and not c.startswith(('sh -c','bash -c','/bin/sh -c')) and 'pgrep' not in c and 'pkill' not in c: out.append(int(d))
    return out
def srvpids(): return [x for x in pids('llama-server') if '--port 8081' in open('/proc/%d/cmdline'%x).read().replace('\0',' ')]
def stop():
    for sig in (signal.SIGTERM,signal.SIGKILL):
        for x in srvpids():
            try: os.kill(x,sig)
            except Exception: pass
        for i in range(30):
            if not srvpids(): break
            time.sleep(1)
    time.sleep(4)
def health():
    try: return urllib.request.urlopen(URL+'/health',timeout=3).status==200
    except Exception: return False
def start(name,flags,cpus,nice):
    stop()
    cmd=(['nice','-n',str(nice)] if nice is not None else [])+(['taskset','-c',cpus] if cpus else [])+[BIN,'-m',M,'--host','127.0.0.1','--port','8081']+flags
    open(O+'/'+name+'.cfg','w').write(' '.join(cmd))
    p=subprocess.Popen(cmd,stdout=open(O+'/'+name+'.srv.log','w'),stderr=subprocess.STDOUT,env={**os.environ,'GGML_CUDA_NO_PINNED':'1'},start_new_session=True,stdin=subprocess.DEVNULL)
    for i in range(300):
        if p.poll() is not None: return False
        if health(): return True
        time.sleep(2)
    return False
def setf(fl,name,val=None):
    fl=list(fl)
    if name in fl:
        i=fl.index(name)
        if val is not None: fl[i+1]=str(val)
        return fl
    fl.append(name)
    if val is not None: fl.append(str(val))
    return fl
def delf(fl,name,hasval=True):
    fl=list(fl)
    if name in fl:
        i=fl.index(name); del fl[i:i+(2 if hasval else 1)]
    return fl
def post(p,n,cache=False,timeout=1500):
    d={'prompt':p,'n_predict':n,'temperature':0,'top_k':1,'cache_prompt':cache,'seed':1}
    r=urllib.request.Request(URL+'/completion',json.dumps(d).encode(),{'Content-Type':'application/json'})
    return json.load(urllib.request.urlopen(r,timeout=timeout))
def s(o):
    t=o['timings']; return dict(pp=round(t['prompt_per_second'],2),tg=round(t['predicted_per_second'],2),pn=t['prompt_n'],gn=t['predicted_n'],ttft=round(t['prompt_ms']/1000,2),dn=t.get('draft_n'),da=t.get('draft_n_accepted'))
def ntok(t): return len(json.load(urllib.request.urlopen(urllib.request.Request(URL+'/tokenize',json.dumps({'content':t}).encode(),{'Content-Type':'application/json'}),timeout=300))['tokens'])
SHORT="Объясни своими словами, чем модель Mixture-of-Experts отличается от плотной модели, и почему она быстрее на процессоре."
def longp(n): return ' '.join("Факт %d: узел %d соединён с узлом %d, значение %d, метка %s."%(i,i*7%101,i*13%97,i*i%1009,'abcdefgh'[i%8]) for i in range(n))+"\nВопрос: чему равно значение в Факте 50 и какая у него метка? Ответь коротко."
LN=[None]
def bench(name,flags,cpus,nice,full=True):
    R={'name':name,'flags':' '.join(flags),'cpus':cpus,'nice':nice}
    try:
        if not start(name,flags,cpus,nice): R['error']='start_failed'; log(name,'START FAILED'); ST['stages'][name]=R; save(); return R
        r=post(SHORT,96); R['short']=s(r); R['short_text']=r['content'][:200]
        if full:
            if LN[0] is None:
                n=105
                for _ in range(4):
                    c=ntok(longp(n)); 
                    if 2850<=c<=3150: break
                    n=int(n*3000/c)
                LN[0]=n
            r=post(longp(LN[0]),48); R['long']=s(r); R['long_text']=r['content'][:100]
            res=[]
            def w(i):
                try: res.append(post("Расскажи подробно про тему номер %d: %s"%(i,['сети','память','звёзды','музыка'][i]),64))
                except Exception as e: res.append(None)
            th=[threading.Thread(target=w,args=(i,)) for i in range(4)]; t=time.time()
            [x.start() for x in th]; [x.join() for x in th]; wall=time.time()-t
            ok=[o for o in res if o]
            R['par4']=dict(agg_tg=round(sum(o['timings']['predicted_n'] for o in ok)/wall,2),per_slot=[round(o['timings']['predicted_per_second'],2) for o in ok],wall=round(wall,1))
    except Exception as e: R['error']=repr(e)[:200]
    log(name,json.dumps({k:R.get(k) for k in ('short','long','par4','error')},ensure_ascii=False)[:600])
    ST['stages'][name]=R; save(); return R
def tgs(R): return (R.get('short') or {}).get('tg',0)
# embed pause
EP=pids('embed_server.py')
def resume():
    for p in EP:
        try: os.kill(p,signal.SIGCONT)
        except Exception: pass
atexit.register(resume)
for p in EP:
    try: os.kill(p,signal.SIGSTOP)
    except Exception: pass
log('embed paused',EP)
# current config
pid=str(srvpids()[0])
argv=open('/proc/%s/cmdline'%pid).read().split('\0')
base=argv[argv.index('8081')+1:]
base=[x for x in base if x]
cpus0=[l.split()[-1] for l in open('/proc/%s/status'%pid) if l.startswith('Cpus_allowed_list')][0]
nice0=os.getpriority(os.PRIO_PROCESS,int(pid))
ST['start_flags']=' '.join(base); ST['start_cpus']=cpus0; ST['start_nice']=nice0; save()
log('base',base,cpus0,nice0)
if cpus0 in ('0-111','0-223'): cpus0=None
# stage1 MTP x ngl
A=bench('A_ngl40_np2',base,cpus0,nice0)
SP=['--spec-type','draft-mtp','--spec-draft-n-max','3']
best=A; cur=base; bestngl=40; ST['mtp_kept']=False
for ngl in (40,36,32,28):
    fb=setf(base,'-ngl',ngl)
    if ngl!=40:
        N=bench('A_ngl%d_np2'%ngl,fb,cpus0,nice0,full=False)
        if 'error' not in N and tgs(N)>tgs(best)*1.03 and not ST['mtp_kept']: best=N; cur=fb
    B=bench('B_mtp3_ngl%d'%ngl,fb+SP,cpus0,nice0,full=(ngl==40))
    if 'error' not in B:
        if tgs(B)>tgs(best)*1.03: best=B; cur=fb+SP; ST['mtp_kept']=True; ST['mtp_text_same']=(B.get('short_text','')[:60]==A.get('short_text','')[:60])
        break
if ST['mtp_kept']:
    for k in ('2','4'):
        R=bench('B_mtp'+k,setf(cur,'--spec-draft-n-max',k),cpus0,nice0,full=False)
        if 'error' not in R and tgs(R)>tgs(best)*1.03: best=R; cur=setf(cur,'--spec-draft-n-max',k)
ST['stage1_flags']=' '.join(cur); save()
# stage2 kvu np4 c32768
C=None
ng0=int(cur[cur.index('-ngl')+1])
for ngl in [x for x in (40,36,32,28,24) if x<=ng0]:
    f=setf(setf(setf(setf(cur,'--parallel',4),'-c',32768),'-ngl',ngl),'-kvu')
    C=bench('C_np4_kvu_ngl%d'%ngl,f,cpus0,nice0)
    if 'error' not in C: cur=f; break
ST['stage2_flags']=' '.join(cur); save()
# stage3 threads / cpus / nice
cands=[('D1_t24_free_nice0',24,None,0),('D2_t24_cpus0-23_nice0',24,'0-23',0),('D3_t16_free_nice0',16,None,0),('D4_t26_free_nice0',26,None,0)]
bt=(cur,cpus0,nice0,C if C and 'error' not in C else best)
for nm,t,cp,nc in cands:
    f=setf(setf(cur,'-t',t),'-tb',t)
    R=bench(nm,f,cp,nc)
    if 'error' not in R and tgs(R)>tgs(bt[3]): bt=(f,cp,nc,R)
cur,cpus_b,nice_b,_=bt
ST['stage3_best']=dict(flags=' '.join(cur),cpus=cpus_b,nice=nice_b); save()
# stage4 KV quality
def mkdoc(seed,target=16600):
    rnd=random.Random(seed); names=['Альфа','Кедр','Орион','Вега','Лотос','Гранит','Янтарь','Сокол']; rnd.shuffle(names)
    codes=[str(rnd.randint(10000,99999)) for _ in range(3)]
    def build(n):
        r2=random.Random(seed); ps=[]
        for i in range(n): ps.append("Отчёт %d по отсеку %s: давление %d, температура %d, журнал ведёт оператор %s, дата %d.%d."%(i,r2.choice(names),r2.randint(90,130),r2.randint(15,40),r2.choice(['Иванов','Петров','Сидоров','Ким']),r2.randint(1,28),r2.randint(1,12)))
        for k,fr in enumerate((0.1,0.5,0.9)): ps.insert(int(n*fr),"ВАЖНО: код доступа отсека %s-%d равен %s."%(names[k],k+1,codes[k]))
        return '\n'.join(ps)
    n=int(target/32)
    for _ in range(5):
        d=build(n); c=ntok(d)
        if target<=c<=target*1.04: break
        n=int(n*target*1.02/c)
    return dict(doc=d,names=names[:3],codes=codes,tokens=c)
DOCS=O+'/kvdocs.json'
def qual(name,flags):
    R=bench(name,flags,cur_cpus,cur_nice,full=False)
    if 'error' in R: return R
    if not os.path.exists(DOCS): json.dump([mkdoc(100+i) for i in range(5)],open(DOCS,'w'),ensure_ascii=False)
    docs=json.load(open(DOCS)); R['docs']=[]; ok=0; tot=0
    for d in docs:
        row=dict(tokens=d['tokens'],ans=[],ok=[])
        for k in range(3):
            q=d['doc']+"\n\nВопрос: чему равен код доступа отсека %s-%d? Ответь только числом.\nОтвет:"%(d['names'][k],k+1)
            try: o=post(q,12,cache=True,timeout=3000); a=o['content'].strip()[:20]; t=s(o)
            except Exception as e: a='ERR'; t={}
            row['ans'].append(a); row['ok'].append(d['codes'][k] in a); tot+=1; ok+=int(d['codes'][k] in a)
            if k==0: row['pp']=t.get('pp'); row['tg']=t.get('tg')
        R['docs'].append(row); log(name,'doc',row); ST['stages'][name]=R; save()
    R['needles_ok']=ok; R['needles_total']=tot; ST['stages'][name]=R; save(); return R
cur_cpus,cur_nice=cpus_b,nice_b
kvb=cur
Q4=qual('Q_q4_0',setf(setf(kvb,'-ctk','q4_0'),'-ctv','q4_0'))
F16=qual('Q_f16',kvb)
Q8=qual('Q_q8_0',setf(setf(kvb,'-ctk','q8_0'),'-ctv','q8_0'))
def sc(R): return R.get('needles_ok',-1)
final=kvb; kvname='f16'
if 'error' not in Q4 and sc(Q4)>=sc(F16) and tgs(Q4)>=tgs(F16)*0.97 and sc(F16)>=0:
    final=setf(setf(kvb,'-ctk','q4_0'),'-ctv','q4_0'); kvname='q4_0'
elif 'error' not in Q8 and sc(Q8)>=sc(F16)>=0 and sc(Q8)>=0 and tgs(Q8)>=tgs(F16)*0.97:
    final=setf(setf(kvb,'-ctk','q8_0'),'-ctv','q8_0'); kvname='q8_0'
ST['kv_choice']=kvname; ST['final_flags']=' '.join(final); ST['final_cpus']=cpus_b; ST['final_nice']=nice_b; save()
# apply
orig=open('/root/nox/start_glm.sh').read().split('\n')
prefix=('nice -n %d '%nice_b if nice_b is not None else '')+('taskset -c %s '%cpus_b if cpus_b else '')
line="GGML_CUDA_NO_PINNED=1 nohup %s%s -m %s --host 127.0.0.1 --port 8081 %s > /root/nox/logs/glm_8081.log 2>&1 &"%(prefix,BIN,M,' '.join(final))
new=[line if 'llama-server' in l and not l.lstrip().startswith('#') else l for l in orig]
subprocess.run(['cp','-a','/root/nox/start_glm.sh','/root/nox/backup/start_glm.sh.before_final'])
open('/root/nox/start_glm.sh','w').write('\n'.join(new))
stop(); resume(); sh("setsid nohup bash /root/nox/start_glm.sh >/root/nox/logs/start_glm_final.log 2>&1 < /dev/null &")
for i in range(200):
    if health(): break
    time.sleep(2)
ST['final_health']=health()
if ST['final_health']:
    try: r=post(SHORT,64); ST['final_short']=s(r)
    except Exception as e: ST['final_short']=repr(e)[:100]
save(); log('ALL DONE health',ST['final_health']); open(O+'/ALL.done','w').write('done')
