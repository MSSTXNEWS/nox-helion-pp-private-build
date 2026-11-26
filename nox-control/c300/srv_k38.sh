echo "C300: srv_k38"
cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo; D=/workspace/nox/ops/dpo
for f in gates_only.py run_dpo.sh train_dpo.py; do curl -s -m 30 "$R/$f?cb=$cb" -o $D/$f; done; chmod +x $D/run_dpo.sh
grep -c loss_weights $D/train_dpo.py; grep -c gates_only $D/run_dpo.sh
/workspace/nox/venv/bin/python -I -m py_compile $D/gates_only.py && echo COMPILED
cat /workspace/nox/state/p3/moe_ab_result.txt 2>&1 | head -8; ls /workspace/nox/agent/autotrain/rounds | tail -2; ls /workspace/nox/STOP 2>&1 | head -1
