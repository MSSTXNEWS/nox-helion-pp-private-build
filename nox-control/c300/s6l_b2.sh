echo "K1: s6l_b2"
N=/workspace/nox
python3 -I - <<'PY'
import json,collections,urllib.request,urllib.parse,re
N="/workspace/nox"
for f in ["ops/dpo/dpo3_train.jsonl","ops/dpo/dpo_inj1_train.jsonl","ops/dpo/dpo_mix.jsonl"]:
    L=open(N+"/"+f,encoding="utf-8",errors="replace").read().splitlines(); c=collections.Counter(); roles=collections.Counter(); n=0; ln=[]
    for l in L:
        try: r=json.loads(l)
        except: continue
        n+=1
        c[tuple(sorted(r.keys()))]+=1
        if isinstance(r.get("prompt"),list): roles[tuple(m.get("role") for m in r["prompt"])]+=1
        if isinstance(r.get("chosen"),list): ln.append(len(r["chosen"][0]["content"]))
        elif isinstance(r.get("chosen"),str): ln.append(len(r["chosen"]))
    print(f,n,dict(c.most_common(2)),dict(roles.most_common(4)),"chosen_len_med",sorted(ln)[len(ln)//2] if ln else None)
def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"nox-s6/1"}),timeout=40).read())
for q in ["sycophancy","anti-sycophancy","antislop","slop","russian roleplay","ru roleplay dialogs","gpt_roleplay_realm","characters_dialogs","persona chat russian"]:
    try: r=get("https://huggingface.co/api/datasets?search=%s&sort=downloads&limit=8&full=false"%urllib.parse.quote(q) if False else "https://huggingface.co/api/datasets?search="+q.replace(" ","+")+"&sort=downloads&limit=8")
    except Exception as e: print("search",q,"err",repr(e)[:60]); continue
    print("## search",q)
    for d in r:
        lic=[t[8:] for t in d.get("tags",[]) if t.startswith("license:")]
        print("  ",d["id"],lic,d.get("downloads"))
PY
echo "## train_dpo roles handling"; T=$(find $N -name train_dpo.py -not -path "*/archive/*" 2>/dev/null | head -1); echo $T; grep -n -i -E "system|apply_chat_template|prompt" $T 2>/dev/null | head -15 | cut -c1-160
echo END
