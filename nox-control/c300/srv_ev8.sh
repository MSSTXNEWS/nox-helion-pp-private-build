#!/bin/bash
E=/workspace/nox/state/p3/eval
cat > $E/deps.sh <<'EOF'
#!/bin/bash
E=/workspace/nox/state/p3/eval; PY=/workspace/nox/venv/bin/python; export PYTHONPATH=$E/pkgs
exec > $E/deps.log 2>&1
for i in $(seq 1 30); do
  m=$($PY -c "from lm_eval import simple_evaluate; from lm_eval.tasks import TaskManager; from lm_eval.models import openai_completions" 2>&1 | grep -oE "No module named '[^']+'" | head -1 | sed -E "s/No module named '([^'.]+).*/\1/")
  [ -z "$m" ] && { echo "deps ok"; break; }
  case $m in sklearn) pkg=scikit-learn;; yaml) pkg=pyyaml;; *) pkg=$m;; esac
  echo "missing $m -> $pkg"; $PY -m pip install -q --no-deps --target $E/pkgs $pkg 2>&1 | tail -1
done
$PY -c "from lm_eval import simple_evaluate; print('IMPORT_OK')" 2>&1 | tail -3
$E/run_eval.sh base
EOF
chmod +x $E/deps.sh; setsid -f $E/deps.sh > /dev/null 2>&1 < /dev/null
sleep 150; tail -12 $E/deps.log | cut -c1-200; tail -5 $E/run_base.log | cut -c1-200
