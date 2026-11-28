echo "K1: s6l_t3"
# только форма данных: имена ключей, типы, длины, счётчики; значений нет
python3 -I - <<'PY'
import json,re,collections,os
N="/workspace/nox"; M=N+"/state/mind"; S=N+"/state/core"
def shape(o,d=0):
    if isinstance(o,dict): return {k:shape(v,d+1) for k,v in list(o.items())[:16]} if d<3 else "dict[%d]"%len(o)
    if isinstance(o,list): return [len(o),shape(o[0],d+1) if o else None] if d<3 else "list[%d]"%len(o)
    if isinstance(o,str): return "str%d"%len(o)
    return type(o).__name__
for f in ["initiative","promises","morning_brief_v5","evening_brief_v5","own_life","rituals","situation"]:
    try: print(f, json.dumps(shape(json.load(open(M+"/"+f+".json",encoding="utf-8"))),ensure_ascii=False)[:600])
    except Exception as e: print(f,"err",type(e).__name__)
d=json.load(open(S+"/self_now.json")); print("self_now keys",list(d.keys()))
for k in ("gratitude","morning_thought","last_talk","top_feeling"): print(k, json.dumps(shape(d.get(k)),ensure_ascii=False)[:300] if k in d else "absent")
L=open(S+"/outbox_owner.jsonl",encoding="utf-8",errors="replace").read().splitlines(); print("outbox_owner lines",len(L))
try: print("outbox keys",json.dumps(shape(json.loads(L[-1])),ensure_ascii=False)[:300])
except Exception: pass
c=collections.Counter()
for l in open(S+"/journal.jsonl",encoding="utf-8",errors="replace"):
    try: c[json.loads(l).get("kind")]+=1
    except Exception: pass
print("journal kinds",c.most_common(14))
PY
echo "## who writes outbox_owner (file names)"; grep -rl "outbox_owner" /workspace/nox/agent /workspace/nox/mods /workspace/nox/canon /workspace/nox/web/pkg/server --include=*.py 2>/dev/null | head -6
echo END
