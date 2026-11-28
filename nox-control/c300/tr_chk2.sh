echo "K1: tr_chk2"
D=/workspace/nox/ops/dpo; N=/workspace/nox
python3 -c "import json;r=json.load(open('$D/dpo_report.json'));print('last_report',r.get('t'),'peak_vram_mib',r.get('peak_vram_mib'),'sec',r.get('sec'),'pairs',r.get('pairs'))" 2>/dev/null
echo "pending=$([ -f $N/state/p3/dpo_pending ] && echo 1 || echo 0) char_only=$([ -f $N/state/p3/char_only ] && echo 1 || echo 0)"
grep -h "char_cycle:" $D/*.log $N/logs/*.log 2>/dev/null | tail -400 | sed -E 's/^[0-9:]+ char_cycle: //; s/[0-9]+/N/g' | sort | uniq -c | sort -rn | head -8
for f in dpo3_train dpo3_eval dpo4_jm dpo_train; do [ -f $D/$f.jsonl ] && echo "$f rows=$(wc -l < $D/$f.jsonl) mtime=$(date -r $D/$f.jsonl +%m%d%H%M)"; done
echo "chat_pairs=$(cat $N/state/chat_pairs/*.jsonl 2>/dev/null | wc -l) dpo_pairs=$(cat $N/state/dpo_pairs/pairs_*.jsonl 2>/dev/null | wc -l)"
echo "vram $(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader)"
echo "accepted_best=$(python3 -c "import json;print(json.load(open('$N/agent/out/ckpt_best_global.json'))['dir'].split('/')[-1])" 2>/dev/null)"
echo END
