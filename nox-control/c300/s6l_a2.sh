echo "K1: s6l_a2"
N=/workspace/nox
python3 -I - <<'PY'
import json,re,collections
N="/workspace/nox"
def mask(s,n=160):
    s=re.sub(r"[A-Za-zЀ-ӿ]","a",s); s=re.sub(r"\d","9",s); return s[:n]
for f in ["state/chat_gate.log","state/chat_judge.log","agent/out/judge.log"]:
    try: L=open(N+"/"+f,encoding="utf-8",errors="replace").read().splitlines()
    except Exception as e: print(f,"err"); continue
    print("##",f,len(L))
    for i in (0,len(L)//2,len(L)-1): print("  ",mask(L[i]))
    c=collections.Counter()
    for l in L:
        for k in ("шаблон","templ","клише","generic","boiler","повтор"):
            if k in l.lower(): c[k]+=1
    print("  kw",dict(c))
f=N+"/state/core/episodes.jsonl"
L=open(f,encoding="utf-8",errors="replace").read().splitlines()
print("## episodes",len(L))
for i in (0,len(L)-1):
    try:
        r=json.loads(L[i]); print("  keys",{k:(type(v).__name__,len(v) if hasattr(v,'__len__') else v) for k,v in r.items()})
    except Exception as e: print("  parse err")
PY
echo "## other candidates"
for f in $N/state/chat_pairs $N/state/chat_pairs.qa; do echo "$f $(stat -c '%F %s' $f)"; done
ls $N/state/chat_pairs 2>/dev/null | head -5; ls $N/state/chat_pairs 2>/dev/null | wc -l
ls $N/state | grep -i -E "turn|dialog|conv|chat_log|episod" | head
ls $N/state/core | grep -i -E "turn|eval|dialog" | head
grep -c . $N/ops/dpo/ab_answers_ebf02c04001131ac.json
echo END
