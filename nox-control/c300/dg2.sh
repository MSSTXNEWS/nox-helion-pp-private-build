echo "K1: dg2 (read-only)"
N=/workspace/nox; D=$N/ops/dpo
echo "--- ps (pid ppid stat etime cmd-basename)"
ps -eo pid,ppid,stat,etimes,args --sort=start_time | grep -E 'char_cycle|autotrain|train_dpo|rel_gates|body_restart|python -I' | grep -v grep | awk '{a=$5; for(i=6;i<=NF&&i<=9;i++) a=a" "$i; gsub(/\/[^ ]*\//,"",a); print $1,$2,$3,$4,a}' | cut -c1-120
echo "--- owner_active"; stat -c '%Y %s' $N/state/orch/OWNER_ACTIVE; echo "now $(date +%s)"
ls -l --time-style=+%m%d-%H:%M $N/state/orch/ 2>/dev/null | awk '{print $6,$7}' | head -12
echo "who touches OWNER_ACTIVE:"; grep -rln "OWNER_ACTIVE" $N/ops $N/agent $N/*.py $N/brain 2>/dev/null | head -8
echo "--- run7.log size $(stat -c %s $D/run7.log) mtime $(date -r $D/run7.log +%m%d-%H:%M)"
echo "--- autotrain.sh refs to char_cycle"; grep -n "char_cycle\|char_only" $N/agent/autotrain/autotrain.sh | cut -c1-170 | head
echo "--- cand_dpo dirs"; ls -ld --time-style=+%m%d-%H:%M $N/distill_v2/ckpt_keep/cand_dpo_* 2>/dev/null | awk '{print $6,$7}' | sed 's#.*/##' | tail
echo "--- latest decision ebf02c04 full structure"
python3 - <<'PY'
import json,re
d=json.load(open("/workspace/nox/distill_v2/gates/decision_ebf02c04001131ac.json"))
r=d.get("rel",{})
print("pass",d.get("pass"),"t",d.get("t"),"cand",d.get("cand","").split("/")[-1],"base",d.get("base","").split("/")[-1])
print("ab",r.get("ab")); print("ext b/c",r.get("ext_base"),r.get("ext_cand")); print("pooled_base",r.get("pooled_base")); print("pooled_cand",r.get("pooled_cand"))
print("drops",r.get("drops"),"new_critical_n",len(r.get("new_critical") or []),"names",[re.sub(r"[^A-Za-z0-9_:.\-]","",str(x))[:30] for x in (r.get("new_critical") or [])][:10])
print("reasons_n",len(d.get("reasons") or []),"warnings_n",len(d.get("warnings") or []))
PY
echo "--- axis_rollback records"
python3 - <<'PY'
import json
for l in open("/workspace/nox/state/p3/axis_rollback.jsonl"):
    r=json.loads(l); print({k:(v if isinstance(v,(int,float,bool)) or (isinstance(v,str) and len(v)<30) else type(v).__name__) for k,v in r.items()})
PY
echo "--- hold/frozen"; wc -l $N/distill_v2/hold_frozen_v1.jsonl | awk '{print "hold_frozen rows",$1}'
echo "--- run2/run6 traceback kinds"; for f in run2 run6; do grep -A30 Traceback $D/$f.log | grep -E '^[A-Za-z_.]+(Error|Exception)|^\s+File' | sed -E 's/^\s+File "([^"]*)", line ([0-9]+).*/\1:\2/; s/^([A-Za-z_.]+(Error|Exception)).*/\1/' | sed 's#.*/##' | tail -4 | tr '\n' ' '; echo; done
echo "--- run6 tail (numbers/status lines only)"; tail -40 $D/run6.log | grep -oE "(train_loss|loss|rc|step|steps|Error|OOM)[^ ,}]{0,20}" | head -12 | tr '\n' ' '; echo
echo "--- step 126 meaning"
python3 - <<'PY'
import json
for f in ("/workspace/nox/agent/out/ckpt_best_global.json","/workspace/nox/state/dispatcher_state.json"):
    try:
        d=json.load(open(f)); print(f.split("/")[-1],{k:(v if isinstance(v,(int,float,bool)) else (v.split("/")[-1][:40] if isinstance(v,str) and len(v)<120 else type(v).__name__)) for k,v in list(d.items())[:25]})
    except Exception as e: print(f,type(e).__name__)
PY
echo "--- distill training status"; ls -lt --time-style=+%m%d-%H:%M $N/distill_v2/*.log $N/distill_v2/state* 2>/dev/null | head -5 | awk '{print $6,$7}' | sed 's#.*/##'
pgrep -fa 'distill_v2' | awk '{print $2,$3,$4,$5}' | sed 's#/[^ ]*/##g' | head
echo END
