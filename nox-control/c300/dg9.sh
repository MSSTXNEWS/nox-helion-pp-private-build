echo "K1: dg9"
ps -eo pid,ppid,stat,etimes,args | grep -E 'distill_v2.py (gen|judge|prep|train)|train_dpo.py|rel_gates.py|gates_only.py|ext_eval.py' | grep -v grep | awk '{a=$5" "$6" "$7; print $1,$2,$3,$4,a}' | sed 's#/[^ ]*/##g' | cut -c1-140
echo "vram $(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits) 8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health)"
echo END
