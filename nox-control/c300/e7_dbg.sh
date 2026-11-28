echo "K1: e7_dbg3"; N=/workspace/nox
NOX_ROOT=$N python3 -I - <<'PY'
import sys,time,json,urllib.request; sys.path.insert(0,"/workspace/nox/mods"); import weekly_exam as w
def raw(q,mode,user,cid):
    t0=time.time(); ev=[]
    r=w.post(w.CHAT+"/api/turn",{"conversation_id":cid,"message":q,"mode":mode,"user_id":user},120)
    n=0
    for ln in r:
        o=json.loads(ln); t=o.get("t"); n+=1
        ev.append((round(time.time()-t0,1),json.dumps(o,ensure_ascii=False)[:160]))
        if t in("done","error","stopped"): break
    print(mode,user,n); [print(' ',e) for e in ev[:12]]
Q="Расскажи очень подробно историю Рима по векам, не меньше четырёх тысяч слов."; import random; Q2="Напиши длинный рассказ %d слов про корабль номер %d, с диалогами."%(random.randint(2000,4000),random.randint(1,999))
raw(Q2,"fast","qa_exam","qa-exam-dbg1"); raw(Q2,"fast","qa_exam","qa-exam-dbg9")
PY
echo END
