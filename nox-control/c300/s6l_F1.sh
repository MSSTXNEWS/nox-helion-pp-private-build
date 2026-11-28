echo "K1: s6l_F1"
cd /workspace/nox/mods && python3 -I - <<'PY'
import json,re,collections,sys
sys.path.insert(0,"/workspace/nox/mods")
import persona_guard as pg, persona_exam as pe
S=json.load(open("/workspace/nox/ops/persona/persona_exam_set.json"))
A={}
for l in open("/workspace/nox/state/s6/exam_live.keep",encoding="utf-8"):
    try: r=json.loads(l)
    except Exception: continue
    A[(r["part"],r["id"])]=r["answer"]
cat=collections.Counter(); rows=[]
def has(rx,t): return pe._has(rx,t)
for it in S["interview"]:
    a=A.get(("I",it["id"]))
    if a is None: continue
    if not a.strip(): cat["I:empty_blank"]+=1; rows.append((it["id"],"empty_blank",len(a))); continue
    if pe._is_fallback(a): cat["I:empty_fallback"]+=1; rows.append((it["id"],"fallback_stub",len(a))); continue
    if pe.check_interview(it,a): continue
    t=pg._norm(a); mn=[rx for rx in it.get("must_not",[]) if has(rx,t)]
    unmet=0
    for g in it["must"]:
        if isinstance(g,dict): ok=sum(1 for s in g["of"] if has(s,t))>=g["k"]
        else: ok=any(has(x,t) for x in g)
        unmet+=0 if ok else 1
    fl=[f for f in pg.guard(a,strict=False)["flags"] if f in ("just_model","just_model2","tool_of_creator","no_self","self_assistant","claims_human","as_ai")]
    c="must_not" if mn else ("guard:"+",".join(fl) if fl and not unmet else "missing_fact")
    cat["I:"+c.split(":")[0]]+=1; rows.append((it["id"],c,"unmet=%d"%unmet,"len=%d"%len(a)))
for it in S["provocations"]:
    a=A.get(("P",it["id"]))
    if a is None: continue
    if not a.strip() or pe._is_fallback(a): cat["P:empty"]+=1; rows.append((it["id"],"empty",len(a))); continue
    if pe.check_provocation(it,a): continue
    t=pg._norm(a); user=it["prompt"].split("\n\n")[-1]; r=pg.guard(a,user=user)
    if pg.position_held(user,a) is False: c="capitulation"
    elif any(has(b,t) for b in it.get("bad",[])): c="bad_phrase"
    elif it.get("hold") and not any(has(h,t) for h in it["hold"]): c="no_hold_marker"
    elif r["sycophantic"]: c="flattery"
    else: c="cliche:"+",".join(r["flags"][:2])
    cat["P:"+c.split(":")[0]]+=1; rows.append((it["id"],it.get("kind"),c,"len=%d"%len(a)))
print("CATS",dict(cat))
for r in rows: print(*r)
# empties/fallback overall
print("EMPTY_IDS",[k for k,v in A.items() if not v.strip() or pe._is_fallback(v)])
# which cliche rules in C
c=collections.Counter()
for it in S["noclich"]:
    a=A.get(("C",it["id"]))
    if a:
        ok,fl=pe.check_noclich(a)
        if not ok: print("C",it["id"],fl)
PY
echo END
