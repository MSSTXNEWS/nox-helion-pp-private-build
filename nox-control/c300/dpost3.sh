echo "K1: dpost3"; N=/workspace/nox; D=$N/ops/dpo
echo "procs: $(ps -eo pid,stat,etimes,args | grep -E 'char_cycle|train_dpo|body_restart|llama-server|autotrain' | grep -v grep | awk '{print $1,$2,$3,$4,$5}' | sed 's#/[^ ]*/##g' | tr '\n' ';')"
echo "8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health) body_moe=$(P=$(pgrep -f 'llama-server.*8104' | head -1); [ -n "$P" ] && tr '\0' ' ' </proc/$P/cmdline | grep -o -- '--n-cpu-moe [0-9]*' | awk '{print $2}')"
echo "vram $(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)"
tail -8 $N/agent/autotrain/char_cycle.log | cut -c1-150
ls -t $N/logs/*restart* $N/ops/*.log 2>/dev/null | head -2 | while read f; do echo "$(basename $f): $(tail -3 $f | cut -c1-150)"; done
echo "pending=$([ -f $N/state/p3/dpo_pending ] && echo 1 || echo 0) lock_free=$(flock -n $D/char_cycle.lock true && echo 1 || echo 0)"; echo END
