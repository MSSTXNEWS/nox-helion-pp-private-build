echo "C300: srv_k25"
/workspace/nox/venv/bin/python -I - <<'PY' 2>&1 | grep -v Warn | tail -12
from trl import DPOConfig
import dataclasses
f=DPOConfig.__dataclass_fields__
print([k for k in f if 'loss' in k or 'rpo' in k or 'sft' in k or 'ref' in k or 'precomp' in k])
print(f['loss_type'].default, f['loss_type'].metadata.get('help','')[:500])
PY
