echo "C300: srv_k24"
cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo; D=/workspace/nox/ops/dpo; mkdir -p $D
for f in build_dpo.py train_dpo.py run_dpo.sh; do curl -s -m 30 "$R/$f?cb=$cb" -o $D/$f; done; chmod +x $D/run_dpo.sh; wc -l $D/*
cd $D; /workspace/nox/venv/bin/python -I -m py_compile build_dpo.py train_dpo.py && echo COMPILED
/workspace/nox/venv/bin/python -I build_dpo.py 2>&1 | tail -5
wc -l dpo_train.jsonl dpo_eval.jsonl; head -c 600 dpo_train.jsonl
/workspace/nox/venv/bin/python -I -c "import trl,inspect;from trl import DPOConfig;f=DPOConfig.__dataclass_fields__;print([k for k in ('precompute_ref_log_probs','rpo_alpha','loss_type','max_length','beta') if k in f])"
