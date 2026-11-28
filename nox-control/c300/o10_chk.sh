echo "K1: o10_chk"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; M=$N/mods
supervisorctl status nox_organism nox_predator
python3 -I $M/nox_predator.py --scan-once
python3 -I $M/nox_predator.py --reflect-once
python3 -I - <<'PY'
import sys,json,time; sys.path.insert(0,"/workspace/nox/mods")
import nox_org_common as C, nox_absorb as AB, nox_ledger as L, nox_predator as P
r="/workspace/nox"
print("hunger_v2",{k:v for k,v in (C.load_json(r+"/state/core/hunger_v2.json") or {}).items() if k!="note"})
sn=C.load_json(r+"/state/core/self_now.json"); print("self_now hunger",sn.get("hunger"),"hunt_queue pending",sn.get("hunt_queue",{}).get("pending"),"gratitude",sn.get("gratitude"))
print("states",[(s["name"],s["intensity"]) for s in sn["pad"]["states"]]); tf=sn["top_feeling"]; print("top",tf and (tf["name"],tf["intensity"],tf["cause"]),"resolved",bool(tf and C.resolve(r,tf["cause"])))
hs=[s for s in sn["pad"]["states"] if s["name"]=="голод"]; print("hunger_cause_resolved",[bool(C.resolve(r,s["cause"])) for s in hs])
print("drive ПОИСК",sn["drives"]["ПОИСК"])
hr=C.load_json(r+"/state/core/hunt_requests.json") or {"requests":[]}; print("hunt_requests",len(hr["requests"]),[(q["status"],q["license"],q["name"][:40]) for q in hr["requests"][:4]])
cs=C.jl_tail(r+"/state/mind/worm_candidates.jsonl",200); import collections; print("candidates",len(cs),dict(collections.Counter(c["license_class"] for c in cs)),dict(collections.Counter(c["found_by"] for c in cs)))
mb=C.load_json(r+"/state/mind/morning_brief_v5.json"); print("morning hunt",mb.get("hunt") and {k:mb["hunt"][k] for k in("pending","hunger")}, "lines_kept",len(mb.get("lines",[])))
print("audit",AB.audit(r)); print("ledger",L.verify(r)); print("reflection",C.load_json(r+"/state/mind/reflection_daily.json"))
print("forge",len(C.jl_tail(r+"/state/core/forge_proposals.jsonl",50)),"lessons_gate",sum(1 for d in C.jl_tail(r+"/state/mind/nrem_lessons.jsonl",200) if d.get("source")=="gate_reflection"))
PY
tail -2 $N/logs/nox_predator.log | cut -c1-200; echo "disk $(df -BM /workspace | tail -1 | awk '{print $4}')"; echo END
