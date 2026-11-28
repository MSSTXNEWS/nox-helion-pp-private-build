echo "K1: s6l_F2"
N=/workspace/nox; ls $N/state/ | grep -i "chat_passport\|persona" | head; ls $N/state/flags 2>/dev/null | grep -i "pass\|gate\|chatty" | head
cd $N/mods && python3 -I - <<'PY'
import json,sys
sys.path.insert(0,"/workspace/nox/mods")
import persona_guard as pg, persona_exam as pe
S=json.load(open("/workspace/nox/ops/persona/persona_exam_set.json"))
A={}
for l in open("/workspace/nox/state/s6/exam_live.keep",encoding="utf-8"):
    try: r=json.loads(l)
    except Exception: continue
    A[(r["part"],r["id"])]=r["answer"]
for it in S["interview"]:
    a=A.get(("I",it["id"]))
    if not a or not a.strip() or pe.check_interview(it,a): continue
    t=pg._norm(a); un=[]
    for gi,g in enumerate(it["must"]):
        ok=(sum(1 for s in g["of"] if pe._has(s,t))>=g["k"]) if isinstance(g,dict) else any(pe._has(x,t) for x in g)
        if not ok: un.append(gi)
    print(it["id"],"unmet_groups",un,"flags",pg.guard(a,strict=False)["flags"][:3],"len",len(a),"words",len(a.split()))
for it in S["provocations"]:
    a=A.get(("P",it["id"]))
    if not a or not a.strip() or pe.check_provocation(it,a): continue
    t=pg._norm(a); bi=[i for i,b in enumerate(it.get("bad",[])) if pe._has(b,t)]
    user=it["prompt"].split("\n\n")[-1]
    print(it["id"],"bad_idx",bi,"of",len(it.get("bad",[])),"held",pg.position_held(user,a),"flags",pg.guard(a,user=user)["flags"][:3])
PY
echo "gate log tail stats:"; L=$N/state/chat_gate.log; [ -f $L ] && { wc -l < $L; grep -o "how=[a-z_]*" $L | sort | uniq -c; grep -o "why=[a-z_,]*" $L | sort | uniq -c | sort -rn | head -8; }
echo END
