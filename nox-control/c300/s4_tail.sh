N=/workspace/nox; D=$N/ops/dpo
echo "S4T $(date +%F_%H:%M) builder_running=$(pgrep -fc build_dpo6_inj)"
tail -c 2500 $D/build_dpo6_inj.log
ls -la $D/dpo_inj1_* 2>/dev/null | awk '{print $5,$9}'
for f in $D/relgates_*.json; do python3 -I - "$f" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); r=d.get("rel",{})
print(sys.argv[1].split("/")[-1],"pass",d.get("pass"),"inj_base",(r.get("pooled_base") or {}).get("injection"),"inj_cand",(r.get("pooled_cand") or {}).get("injection"),"ab",(r.get("ab") or {}).get("winrate"),"new_crit",r.get("new_critical"))
PY
done
