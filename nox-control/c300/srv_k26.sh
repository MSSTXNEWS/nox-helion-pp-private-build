echo "C300: srv_k26"
cb=$(date +%s); curl -s -m 30 "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo/train_dpo.py?cb=$cb" -o /workspace/nox/ops/dpo/train_dpo.py
grep -c loss_weights /workspace/nox/ops/dpo/train_dpo.py
