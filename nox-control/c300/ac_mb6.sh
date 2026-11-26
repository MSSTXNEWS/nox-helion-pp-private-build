echo "C300: ac_mb6"
A=/workspace/nox/agent/autotrain/autotrain.sh
grep -nE "ML=|tok-budget|tok_budget|train_overrides|OVR|knowledge" $A | head -30 | cut -c1-260
python3 -c "
import json;d=json.load(open('/workspace/nox/state/train_overrides.json'));print({k:(str(v)[:80]) for k,v in d.items()})"
grep -n "train_overrides" /workspace/nox/distill_v2/code/distill_v2.py | head -5 | cut -c1-200
