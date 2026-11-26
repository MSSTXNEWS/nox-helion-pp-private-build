echo "C300: ac_mb3"
F=/workspace/nox/distill_v2/code/distill_v2.py
grep -nE "budget *=|--budget|budget\"|tok_budget|\"budget|pack_budget|knowledge_budget|BUDGET" $F | head -20 | cut -c1-220
grep -nE "add_argument\(\"--(max-len|budget|tokens|pack|bs|batch)" $F | cut -c1-200
ps -o args= -p $(pgrep -f "distill_v2.py train"|head -1) | cut -c1-300
grep -n "distill_v2.py train" /workspace/nox/agent/autotrain/autotrain.sh /workspace/nox/ops/autotrain.sh 2>/dev/null | head -3 | cut -c1-300
python3 -c "
import json;d=json.load(open('/workspace/nox/ops/v5_knowledge_gpu_20261125/knowledge.json'));print({k:(v if not isinstance(v,(list,dict)) else type(v).__name__) for k,v in d.items()})" | cut -c1-600
