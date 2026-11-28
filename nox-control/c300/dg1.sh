echo "K1: dg1 (read-only)"
N=/workspace/nox; D=$N/ops/dpo; ST=$N/state/p3; A=$N/agent/autotrain
echo "pending=$([ -f $ST/dpo_pending ] && echo 1 || echo 0) pending_age_s=$(( $(date +%s) - $(stat -c %Y $ST/dpo_pending 2>/dev/null || echo 0) )) char_only=$([ -f $ST/char_only ] && echo 1 || echo 0) STOP=$([ -e $N/STOP ] && echo 1 || echo 0) window_off=$([ -e $N/state/train_window.off ] && echo 1 || echo 0)"
echo "LIVE_TURN=$([ -e $N/agent/LIVE_TURN ] && echo 1 || echo 0) owner_active=$([ -e $N/state/orch/OWNER_ACTIVE ] && echo 1 || echo 0) owner_age_s=$(( $(date +%s) - $(stat -c %Y $N/state/orch/OWNER_ACTIVE 2>/dev/null || echo 0) ))"
echo "cmds gpu0=$([ -f $A/donor_hybrid.cmd.gpu_ncmoe0 ] && echo 1 || echo 0) hyb22=$([ -f $A/donor_hybrid.cmd.liska_ncmoe22 ] && echo 1 || echo 0) body_restart=$([ -f $N/ops/body_restart.sh ] && echo 1 || echo 0)"
echo "vram(used,total,free MiB): $(nvidia-smi --query-gpu=memory.used,memory.total,memory.free --format=csv,noheader,nounits)"
echo "load=$(cut -d' ' -f1 /proc/loadavg) disk_free_G=$(df --output=avail -BG $N | tail -1 | tr -dc 0-9)"
echo "locks: char_cycle_lock_held=$(flock -n $D/char_cycle.lock true && echo 0 || echo 1)"
echo "procs: $(pgrep -fa 'distill_v2.py|train_dpo.py|rel_gates.py|gates_only.py|ext_eval.py|char_cycle.sh|autotrain.sh' | awk '{print $2" "$3}' | sed 's#.*/##' | sort | uniq -c | tr '\n' ';')"
echo "--- who calls char_cycle"; grep -n "char_cycle\|char_only" $A/../../ops/autotrain.sh $N/ops/*.sh 2>/dev/null | cut -c1-160 | head -8
echo "--- logs mtime"; ls -l --time-style=+%m%d-%H:%M $D/*.log $N/logs/*train* $N/logs/*char* 2>/dev/null | awk '{print $6,$7,$5}' | tail -15
echo "--- char_cycle msgs (last 40, digits kept)"; grep -h "char_cycle:" $D/*.log $N/logs/*.log 2>/dev/null | cut -c1-140 | tail -40
echo "--- data"
for f in dpo3_train dpo3_eval dpo4_jm dpo_train; do [ -f $D/$f.jsonl ] && echo "$f rows=$(wc -l < $D/$f.jsonl) mtime=$(date -r $D/$f.jsonl +%m%d-%H:%M)"; done
echo "chat_pairs=$(cat $N/state/chat_pairs/*.jsonl 2>/dev/null | wc -l) dpo_pairs=$(cat $N/state/dpo_pairs/pairs_*.jsonl 2>/dev/null | wc -l)"
python3 - <<'PY'
import json,glob
D="/workspace/nox/ops/dpo"
for f in ("build5_stats.json","dpo_report.json"):
    try:
        r=json.load(open(D+"/"+f)); print(f,{k:v for k,v in r.items() if isinstance(v,(int,float,str)) and k!="out" and len(str(v))<40})
    except Exception as e: print(f,type(e).__name__)
PY
echo "--- candidates / decisions"
ls -td $N/distill_v2/ckpt_keep/cand_dpo_* 2>/dev/null | head -5 | while read c; do echo "$(basename $c) st=$(ls $c 2>/dev/null | wc -l) adapter=$([ -s $c/adapter_model.safetensors ] && echo 1 || echo 0)"; done
ls -lt --time-style=+%m%d-%H:%M $N/distill_v2/gates/decision_*.json 2>/dev/null | head -6 | awk '{print $6,$7}'
for f in $(ls -t $N/distill_v2/gates/decision_*.json 2>/dev/null | head -4); do python3 - "$f" <<'PY'
import json,sys,re
d=json.load(open(sys.argv[1])); r=d.get("rel") or {}
print(sys.argv[1].split("decision_")[1][:16],"pass=",d.get("pass"),"ab=",(r.get("ab") or {}).get("winrate"),"drops=",r.get("drops"),"pooled_all b/c=",(r.get("pooled_base") or {}).get("_all"),(r.get("pooled_cand") or {}).get("_all"),"n_reasons=",len(d.get("reasons") or []),"reason_kinds=",sorted({re.split(r"[ :]",x)[0] for x in d.get("reasons") or []}))
PY
done
echo "ab_answers=$(ls $D/ab_answers_*.json 2>/dev/null | wc -l) relgates=$(ls $D/relgates_*.json 2>/dev/null | wc -l)"
echo "--- accepted / cand dirs (autotrain)"
echo "accepted=$(ls -d $A/accepted* 2>/dev/null | wc -l) cand=$(ls -d $A/cand* 2>/dev/null | wc -l)"; ls $A | head -40 | tr '\n' ' '; echo
python3 -c "import json;d=json.load(open('$N/agent/out/ckpt_best_global.json'));print('best_dir',d['dir'].split('/')[-1],'accepted_by',d.get('accepted_by'),'at',d.get('accepted_at'),'step',d.get('step'))" 2>&1 | cut -c1-200
ls $ST/axis_rollback.jsonl 2>/dev/null && python3 -c "
import json
for l in list(open('$ST/axis_rollback.jsonl'))[-3:]:
    r=json.loads(l);print(r.get('cand_sha16','')[:8],r.get('verdict'))"
echo "--- step 126"
grep -rIl "126" $N/state/p3/*.json $N/agent/out/*.json $N/state/*.json 2>/dev/null | head -5
grep -rhoE "(step|шаг)[^0-9]{0,6}126\b.{0,40}" $N/logs $D/*.log $N/state/p3 2>/dev/null | tr -d '"' | head -5 | cut -c1-90
ls $N/distill_v2/ckpt_keep | sed -E 's/hold[0-9.]+_[0-9]+//' | head -30 | tr '\n' ' '; echo
grep -h "autotrain\|running" $N/state/p3/*status*.json $A/status*.json 2>/dev/null | head -3 | cut -c1-160
echo "--- errors in run*.log (type + file:line only)"
for f in $D/run*.log $N/logs/*train*.log; do [ -f $f ] || continue; echo "$(basename $f) oom=$(grep -ci 'out of memory\|OutOfMemory' $f) tb=$(grep -c 'Traceback' $f)"; done 2>/dev/null | head -12
grep -h -B1 -E '^[A-Za-z_.]*(Error|Exception)\b' $D/run7.log 2>/dev/null | grep -E '^\s+File|^[A-Za-z_.]*(Error|Exception)' | sed -E 's/^\s+File "([^"]*)", line ([0-9]+).*/\1:\2/; s/^([A-Za-z_.]*(Error|Exception)).*/\1/' | sed 's#.*/##' | tail -12
echo "run7 tail kinds:"; tail -300 $D/run7.log 2>/dev/null | grep -oE "(Traceback|OOM|out of memory|rc=[0-9]+|loss'?: ?[0-9.]+|train_loss'?: ?[0-9.]+|ОТНОСИТЕЛЬНЫЕ ВОРОТА: [^ ]+|НЕ принимаю|ПРИНЯТ|ROLLBACK)" | sort | uniq -c | sort -rn | head -12
echo "--- supervisor"; supervisorctl status 2>/dev/null | grep -iE "dpo|train|autotrain|char|8104|chat|body" | awk '{print $1"="$2}' | tr '\n' ' '; echo
echo "cron/loop calling autotrain: $(pgrep -fc 'autotrain')"; 
echo END
