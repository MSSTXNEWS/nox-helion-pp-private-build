echo "K1: dpst"; N=/workspace/nox; D=$N/ops/dpo; ST=$N/state/p3; A=$N/agent/autotrain
echo "procs: $(ps -eo pid,stat,etimes,args | grep -E 'char_cycle|train_dpo|rel_gates|body_restart' | grep -v grep | awk '{print $1,$2,$3,$4,$5}' | sed 's#/[^ ]*/##g' | tr '\n' ';')"
UM=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits); echo "vram pct=$(( ${UM%%,*}*100/${UM##*, } )) 8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) body_moe=$(P=$(pgrep -f 'llama-server.*8104' | head -1); tr '\0' ' ' </proc/$P/cmdline | grep -o -- '--n-cpu-moe [0-9]*' | awk '{print $2}')"
echo "pending=$([ -f $ST/dpo_pending ] && echo 1 || echo 0) vram_abort=$([ -e $ST/dpo_vram_abort ] && echo 1 || echo 0) disk_G=$(df --output=avail -BG $N | tail -1 | tr -dc 0-9)"
tail -6 $A/char_cycle.log | cut -c1-150
echo "mix: $(grep -ao 'mix rows [0-9]* main [0-9]* inj [0-9]* pers [0-9]* replay [0-9]*' $D/run7.log | tail -1)"
echo "progress: $(tail -c 3000 $D/run7.log | tr '\r' '\n' | grep -aE '[0-9]+/[0-9]+ \[' | tail -1 | cut -c1-110)"
echo "loss lines: $(tail -c 20000 $D/run7.log | tr '\r' '\n' | grep -aoE "'loss': [0-9.]+|train_loss': [0-9.]+" | tail -3 | tr '\n' ' ')"
echo "report: $(python3 -c "import json;r=json.load(open('$D/dpo_report.json'));print(r.get('t'),'loss',r.get('loss'),'steps',r.get('steps'),'sec',r.get('sec'),'peak',r.get('peak_vram_mib'),'pairs',r.get('pairs'))")"
ls -t $N/distill_v2/gates/decision_*.json | head -1 | sed 's#.*/##'
echo END
