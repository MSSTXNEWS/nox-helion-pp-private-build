echo "K1: s6l_a3"
N=/workspace/nox
echo "## where 5713"; grep -rl "5713" $N/state --include=*.json --include=*.log --include=*.txt 2>/dev/null | head -8
python3 -I - <<'PY'
import json,re,collections
N="/workspace/nox"
L=open(N+"/state/core/episodes.jsonl",encoding="utf-8",errors="replace").read().splitlines()
kc=collections.Counter(); ck=collections.defaultdict(collections.Counter); ln=collections.defaultdict(list)
for l in L:
    try: r=json.loads(l)
    except: continue
    k=(r.get("src"),r.get("kind")); kc[k]+=1
    c=r.get("content")
    if isinstance(c,dict):
        for kk,v in c.items():
            ck[k][kk]+=1
            if isinstance(v,str): ln[(k,kk)].append(len(v))
print("## episodes src/kind:", kc.most_common(12))
for k,cnt in list(ck.items())[:8]: print(k, dict(cnt))
# gate log: flags vocabulary
G=open(N+"/state/chat_gate.log",encoding="utf-8",errors="replace").read().splitlines()
fl=collections.Counter(); how=collections.Counter()
for l in G:
    m=re.search(r"flags=\[(.*?)\] how=(\w+)",l)
    if m:
        how[m.group(2)]+=1
        for f in re.findall(r"'([^']{1,90})'",m.group(1)): fl[re.sub(r"\d+","9",f)]+=1
    m=re.search(r" why=(.*?) variants=",l)
print("## gate how",dict(how)); print("## gate flags top:")
for f,c in fl.most_common(25): print(c, f)
# judge log chat_judge: tags
J=open(N+"/state/chat_judge.log",encoding="utf-8",errors="replace").read().splitlines()
tg=collections.Counter()
for l in J:
    for t in re.findall(r'"tags": \[(.*?)\]',l): tg[t]+=1
    for t in re.findall(r'"flags": \[(.*?)\]',l): tg["F:"+t]+=1
print("## judge tags", tg.most_common(10))
PY
echo "## judge-ish JSON counts of шаблон"
grep -rIl -i "шаблон" $N/state/core $N/state/inspector $N/state/logs 2>/dev/null | head -8
echo END
