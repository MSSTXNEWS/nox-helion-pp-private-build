echo "K1: tr_chk1"
curl -s -m 8 http://127.0.0.1:18091/api/nox/training/status | python3 -c "
import json,sys;o=json.load(sys.stdin)
for k in ('status','phase','verdict','round','step','best','accepted','last_gates','rows_total','new_rows','total_min','checkpoint_count','receipt_age_seconds','cycle'): print(k,o.get(k))
print('note_len',len(str(o.get('note') or '')))"
ls -t /workspace/nox/state/best 2>/dev/null | head -3 | wc -l
echo "best_dir_files=$(ls /workspace/nox/state/best 2>/dev/null | wc -l)"
L=$(ls -t /workspace/nox/ops/dpo/*.log /workspace/nox/logs/*dpo* /workspace/nox/logs/*char_cycle* 2>/dev/null | head -1)
echo "log_found=$([ -n "$L" ] && echo yes || echo no)"
[ -n "$L" ] && grep -oiE "(gate[a-z_]*|win_rate|winrate|delta|margin|reward_acc|soul_fail|critical)[=: ]+[-0-9.]+" "$L" | tail -20 | sort | uniq -c | tail -20
echo "models_cand=$(du -csh /workspace/nox/models/cand_* 2>/dev/null | tail -1)"
echo END
