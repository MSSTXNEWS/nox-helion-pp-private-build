echo "K1: o6_chk"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; M=$N/mods; S=$N/state/core
supervisorctl status nox_organism
python3 -I - <<'PY'
import sys,json,time,os,shutil,tempfile,hashlib
sys.path.insert(0,"/workspace/nox/mods")
import nox_org_common as C, nox_ledger as L
r="/workspace/nox"
T=C.jl_tail(r+"/state/core/organism_tick.jsonl",400)
print("ticks",len(T),"span_min",round((C.parse_ts(T[-1]["ts"])-C.parse_ts(T[0]["ts"]))/60,1))
for k in ("DA","NE","5-HT","ACh","CORT","OXT"):
    xs=[t["panel"][k] for t in T]; print(k,"first",xs[0],"last",xs[-1],"min",min(xs),"max",max(xs),"distinct",len(set(xs)))
print("F first/last",T[0]["F"],T[-1]["F"],"distinct",len({t["F"] for t in T}),"PAD last",T[-1]["pad"])
print("drives last",T[-1]["drives"])
sn=C.load_json(r+"/state/core/self_now.json")
print("self_now age_s",round(time.time()-C.parse_ts(sn["organism_ts"])),"old_keys_kept",all(k in sn for k in ("telemetry","feelings","text","aliveness_score","training","hardware")))
print("last_talk",sn["last_talk"]["text"],"| top",(sn["top_feeling"] or {}).get("name"),(sn["top_feeling"] or {}).get("intensity"))
ok=0;bad=0
for s in sn["pad"]["states"]+([sn["top_feeling"]] if sn["top_feeling"] else []):
    rec=C.resolve(r,s["cause"]); 
    if rec: ok+=1; print("  cause",s["name"],s["cause"],"-> journal kind",rec.get("kind"),"sid",rec.get("sid"),"value",rec.get("value"))
    else: bad+=1; print("  cause_MISSING",s["name"],s["cause"])
print("causes_resolved",ok,"missing",bad)
print("journal organism lines",sum(1 for d in C.jl_tail(r+"/state/core/journal.jsonl",5000) if d.get("kind")=="organism"))
print("ledger",L.verify(r))
# сон на копии (боевые файлы не трогаем)
import nox_sleep as SL
tmp=tempfile.mkdtemp()
for d in ("state/core","state/mind","state/agents"): os.makedirs(tmp+"/"+d)
shutil.copy(r+"/state/core/episodes.jsonl",tmp+"/state/core/episodes.jsonl"); shutil.copy(r+"/state/core/self_now.json",tmp+"/state/core/self_now.json")
if os.path.exists(r+"/state/agents/sleep_cursor.json"): shutil.copy(r+"/state/agents/sleep_cursor.json",tmp+"/state/agents/sleep_cursor.json")
res=SL.run(tmp,time.time()); print("sleep_copy",res)
ids={json.loads(l).get("id") for l in open(r+"/state/core/episodes.jsonl",encoding="utf-8",errors="ignore") if l.strip().startswith("{")}
hy=[json.loads(l) for l in open(tmp+"/state/mind/rem_hypotheses.jsonl")]; print("hyp",len(hy),"status",{h["status"] for h in hy},"evidence_real",all(e in ids for h in hy for e in h["evidence"]))
ls=[json.loads(l) for l in open(tmp+"/state/mind/nrem_lessons.jsonl")]; print("lessons",len(ls),"weights",[l["weight"] for l in ls],"evidence_real",all(e in ids for l in ls for e in l["evidence"]))
c=C.load_json(tmp+"/state/mind/nrem_concepts.json"); print("concepts",c["n"])
print("dream.jsonl real lines",sum(1 for _ in open(r+"/state/mind/dream.jsonl")))
shutil.rmtree(tmp)
PY
tail -3 $N/logs/nox_organism.log | sed -E 's/[А-Яа-я]+/w/g' | cut -c1-200
echo "disk $(df -BG /workspace | tail -1 | awk '{print $4}') free"
echo END
