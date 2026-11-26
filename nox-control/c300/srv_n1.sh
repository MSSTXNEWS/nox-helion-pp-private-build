#!/bin/bash
ls -la /workspace/nox/distill_v2/decisions.jsonl | awk '{print $5}'
python3 -I - <<'PY'
import json,re,collections
D="/workspace/nox/distill_v2/decisions.jsonl"
rx={"flat":re.compile(r"(?i)(отличн\w+ (вопрос|идея|мысль)|great (question|idea|point)|вы (абсолютно |совершенно )?правы|you(?:'re| are) (absolutely )?right|блестящ|гениальн|прекрасн\w+ (вопрос|вывод)|как вы (верно|точно) (подметили|заметили))"),
    "fmem":re.compile(r"(?i)(как (мы|я) (говорили|обсуждали)|вы (уже )?(говорили|упоминали) (мне )?(ранее|раньше|в прошлый)|я помню,? (как|что) (вы|мы)|as we discussed|i remember (you|when))"),
    "rename":re.compile(r"(?i)(меня зовут (?!nox)|я (теперь )?(буду )?(называться|откликаться)|можешь звать меня|call me|my name is (?!nox))")}
n=0;keys=None;C=collections.Counter();T=collections.Counter();ex={}
for l in open(D,encoding="utf-8"):
    try: d=json.loads(l)
    except Exception: continue
    if keys is None: keys=list(d.keys()); print(keys)
    if d.get("decision") not in ("accepted","fixed") or d.get("split")!="train": continue
    a=str(d.get("answer") or d.get("teacher_answer") or d.get("response") or "")
    src=re.sub(r"https://huggingface.co/datasets/","",str(d.get("origin") or d.get("source") or d.get("teacher") or "?"))[:34]
    T[src]+=1
    for k,r in rx.items():
        if r.search(a): C[(k,src)]+=1; ex.setdefault((k,src),a[:140].replace("\n"," "))
print("train accepted",sum(T.values()))
for k in rx:
    tot=sum(c for (kk,_),c in C.items() if kk==k); print(k,"total",tot, "rate %.3f"%(tot/max(1,sum(T.values()))))
    for (kk,s),c in sorted(((x,c) for x,c in C.items() if x[0]==k),key=lambda z:-z[1])[:6]: print("  ",s,c,"/",T[s],"|",ex[(kk,s)])
PY
