echo "K1: q26_stats"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; L=$N/state/chat_gate.log
python3 - <<'PY'
import re,collections,statistics as S
L="/workspace/nox/state/chat_gate.log"
try: ls=open(L,encoding="utf-8",errors="replace").read().splitlines()
except Exception as e: print("nolog"); raise SystemExit
print("lines",len(ls))
dec=[l for l in ls if " cid=" in l and " gen=" in l and " why=" in l]
print("decisions",len(dec))
def num(rx,l):
    m=re.search(rx,l); return float(m.group(1)) if m else None
tot=[num(r"total=([0-9.]+)s",l) for l in dec]; tot=[x for x in tot if x is not None]
gen=[num(r"gen=([0-9.]+)s",l) for l in dec]; gen=[x for x in gen if x is not None]
def q(a,p): a=sorted(a); return round(a[min(len(a)-1,int(len(a)*p))],2) if a else None
print("total med/p90/max",q(tot,.5),q(tot,.9),max(tot) if tot else None,"gen med/p90",q(gen,.5),q(gen,.9))
why=collections.Counter()
for l in dec:
    m=re.search(r"why=(\S+(?: \S+)?)",l); w=m.group(1) if m else "?"
    w=re.sub(r"[^\w=-]","",w.split(":")[0])[:20] or "?"
    why[w]+=1
print("why",dict(why))
nv=sum(1 for l in dec if not re.search(r"variants=-( |$)",l)); print("variants",nv,"of",len(dec))
by=collections.Counter(re.search(r" by=(\S+)",l).group(1) for l in dec if re.search(r" by=(\S+)",l)); print("by",dict(by))
note=collections.Counter(re.search(r" note=(\S+)",l).group(1) for l in dec if re.search(r" note=(\S+)",l)); print("note",dict(note))
je=[l for l in ls if " judge_err " in l]; print("judge_err",len(je))
c=collections.Counter()
for l in je:
    for part in re.split(r"; ",l.split("judge_err ",1)[1]):
        nm=part.split(" ")[0]
        k="other"
        for key,rx in (("timeout",r"timed out|Timeout|timeout"),("http400",r"HTTP Error 400"),("http429",r"HTTP Error 429"),("http5xx",r"HTTP Error 5"),("parse",r"parse"),("conn",r"Connection|URLError|refused|reset"),("nokey",r"KeyError|IndexError")):
            if re.search(rx,part): k=key;break
        c[nm+":"+k]+=1
print("judge_err_kinds",dict(c))
ja=[num(r"after ([0-9.]+)s",l) for l in je]; ja=[x for x in ja if x is not None]; print("judge_err_after med/max",q(ja,.5),max(ja) if ja else None)
for t in ("j8300_err","adv_err","chatty","second_opinion"): print(t,sum(1 for l in ls if " %s "%t in l or l.split(" ",2)[-1].startswith(t)))
ch=[l for l in ls if " chatty " in l]; print("chatty_how",dict(collections.Counter(re.search(r"how=(\w+)",l).group(1) for l in ch if re.search(r"how=(\w+)",l))))
fl=collections.Counter()
for l in ch+dec:
    for f in ("повтор приветствия","дежурный хвост","ассистентский шаблон","самоопровержение","повтор прошлого","вето","выдуманн","неполный","сухо"):
        if f in l: fl[f]+=1
print("flags",dict(fl))
jp=[num(r" j=([0-9.]+)",l) for l in dec]; jp=[x for x in jp if x is not None]; print("j_p med",q(jp,.5),"n",len(jp))
PY
echo "judge8104: $(ss -ltn | grep -c ':8104 ') groq8793: $(ss -ltn | grep -c ':8793 ') vram: $(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | head -1)"
ss -ltnp | grep -E ":(8091|8104|8793|18798|8300|18091) " | awk '{print $4}' | tr "\n" " "; echo
grep -rl "nox-live" $N --include=*.py 2>/dev/null | head -5
echo "train_proc: $(pgrep -fc train_dpo)"; ls $N/state | grep -iE "p3|train|state" | head
echo END
