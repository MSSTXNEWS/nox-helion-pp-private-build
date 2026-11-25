python3 - <<'P'
import json,os,re,time
Q="/workspace/nox/web/site/qa/"
a=json.load(open(Q+"audit.json"))
log=open("/tmp/s5_chain4.log",errors="ignore").read()
done=re.findall(r"DONE (\w+) (\d\d:\d\d)",log)
print("OUT: done",[d[0] for d in done],"chain_done" if "CHAIN_DONE" in log else "")
for k,t in done:
    v=a.get(k,{}); ARU=v.get("ARU") or [None]*3
    ok_aru=all(isinstance(x,(int,float)) and x>=8 for x in ARU)
    bad=[f['item'][:28] for f in v.get('fails',[])]
    txt="АВТО-АУДИТ %s: статус %s, WOW %s, A/R/U(медиана) %s, прогоны %s; провалы: %s. %s"%(t,v.get('status'),v.get('wow'),ARU,v.get('vision_runs'),bad[:6],"Автоматика проходит, нужна ручная сверка с лидером." if ok_aru and not bad else "ВОЗВРАТ.")
    f=Q+"rework/%s.json"%k
    j=json.load(open(f)) if os.path.exists(f) else {"page":k+".html","cycle":v.get("cycle",0),"fails":[]}
    j["s5_auto"]={"ts":time.strftime("%F %T"),"text":txt}
    json.dump(j,open(f,"w"),ensure_ascii=False,indent=1)
    print("OUT:",k,v.get('status'),v.get('wow'),ARU,v.get('vision_runs'),'vend',len(v.get('vendor_used') or []),bad[:5])
P
