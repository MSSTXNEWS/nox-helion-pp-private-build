echo "C300: srv_k68"
cd /workspace/nox/ops/dpo
grep -a "chain4\|rc=\|targeted\|dpo2_train\|cand2\|ПРИНЯТ\|НЕ принят\|ext \|_sec=\|sec=\|верность\|душа\|MIND\|Traceback\|Error:" run2.log | grep -v "pytree\|Tokeniz\|Dropping" | cut -c1-330 | tail -n 40
cat build2_stats.json; echo; python3 -c "
import json;d=json.load(open('dpo_report_round2.json'));print({k:d[k] for k in ('out','steps','sec','loss','pairs')}, d.get('eval',{}).get('eval_rewards/margins'))"
cat ext_eval.json 2>&1 | head -40
cat /workspace/nox/ops/draw/bench_sd.txt
