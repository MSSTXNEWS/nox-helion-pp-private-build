echo "K1: dg6 (read-only)"; N=/workspace/nox; D=$N/ops/dpo; A=$N/agent/autotrain
echo "8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) body_moe=$(P=$(pgrep -f 'llama-server.*8104' | head -1); tr '\0' ' ' </proc/$P/cmdline | grep -o -- '--n-cpu-moe [0-9]*' | awk '{print $2}')"
echo "vram(used,total,free) $(nvidia-smi --query-gpu=memory.used,memory.total,memory.free --format=csv,noheader,nounits)"
echo "gpu procs MiB: $(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | awk -F', ' '{printf "%s=%s ",$1,$2}')"
echo "procs: $(ps -eo pid,stat,etimes,args | grep -E 'char_cycle|train_dpo|rel_gates|body_restart|body_ttft' | grep -v grep | awk '{print $1,$2,$3,$4,$5}' | sed 's#/[^ ]*/##g' | tr '\n' ';')"
echo "lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0) pending=$([ -f $N/state/p3/dpo_pending ] && echo 1 || echo 0) gen_hold=$(ls $N/state/*gen_hold* $N/state/orch/*gen_hold* $N/agent/*gen_hold* 2>/dev/null | wc -l)"
ls $N/state/*gen_hold* $N/state/orch/*gen_hold* $N/agent/*gen_hold* 2>/dev/null | sed 's#/workspace/nox/##'
echo "--- cron lines mentioning body/known_good (names only)"
(crontab -l 2>/dev/null; cat /etc/cron.d/* 2>/dev/null) | grep -E "body_ttft|known_good|body_restart|body_guard|watch" | sed -E 's/^([0-9*\/, -]+ ){5}//' | cut -c1-140
grep -rlE "body_ttft_upgrade" $N/ops $N/state $N/agent --include=*.sh --include=*.py --include=*.conf 2>/dev/null | head -5 | sed 's#/workspace/nox/##'
echo "--- known_good vs hybrid cmd flags (n-cpu-moe/-ngl/ctx)"
for f in donor_hybrid.cmd.known_good donor_hybrid.cmd.gpu_ncmoe0 donor_hybrid.cmd.liska_ncmoe22 donor_hybrid.cmd.p5_best; do [ -f $A/$f ] && echo "$f ncmoe=$(grep -o -- '--n-cpu-moe [0-9]*' $A/$f | head -1) ngl=$(grep -o -- '-ngl [0-9]*' $A/$f | head -1) cpumoe=$(grep -c -- '--cpu-moe\|-cmoe' $A/$f) mtime=$(date -r $A/$f +%m%d-%H:%M)"; done
ls -l --time-style=+%m%d-%H:%M $A/donor_hybrid.cmd $N/agent/autotrain/donor_hybrid.cmd 2>/dev/null | awk '{print $6,$7,$8}'
echo "current donor_hybrid.cmd ncmoe=$(grep -o -- '--n-cpu-moe [0-9]*' $A/donor_hybrid.cmd | head -1) same_as_known_good=$(cmp -s $A/donor_hybrid.cmd $A/donor_hybrid.cmd.known_good && echo 1 || echo 0) same_as_22=$(cmp -s $A/donor_hybrid.cmd $A/donor_hybrid.cmd.liska_ncmoe22 && echo 1 || echo 0)"
echo "off flags: $(ls $N/state/*.off $N/state/orch/*.off 2>/dev/null | xargs -n1 basename 2>/dev/null | tr '\n' ' ')"
echo "--- data"; for f in dpo_inj2_train dpo_inj1_train dpo_pers1_train dpo3_train dpo_train; do echo "$f=$(wc -l < $D/$f.jsonl 2>/dev/null)"; done
echo "disk_free_G=$(df --output=avail -BG $N | tail -1 | tr -dc 0-9) run7_size=$(stat -c %s $D/run7.log)"
tail -6 $A/char_cycle.log | cut -c1-150
echo END
