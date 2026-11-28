echo "K1: e7_dbg2"; N=/workspace/nox
NOX_ROOT=$N python3 -I - <<'PY'
import sys,time,json,urllib.request; sys.path.insert(0,"/workspace/nox/mods"); import weekly_exam as w
def raw(q,mode,user,cid):
    t0=time.time(); ev=[]
    r=w.post(w.CHAT+"/api/turn",{"conversation_id":cid,"message":q,"mode":mode,"user_id":user},120)
    n=0
    for ln in r:
        o=json.loads(ln); t=o.get("t"); n+=1
        if n<=6 or t in("done","error","stopped"): ev.append((round(time.time()-t0,1),t,str(o.get("text") or o.get("delta") or o.get("msg") or "")[:70]))
        if t in("done","error","stopped"): break
    print(mode,user,n,ev[-8:])
Q="Расскажи очень подробно историю Рима по векам, не меньше четырёх тысяч слов."
raw(Q,"fast","qa_exam","qa-exam-dbg1"); raw(Q,"deep","qa_exam","qa-exam-dbg2"); raw(Q,"fast","owner","qa-exam-dbg3")
PY
echo END
