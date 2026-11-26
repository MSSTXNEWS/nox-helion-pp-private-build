#!/bin/bash
E=/workspace/nox/state/p3/eval; mkdir -p $E/tasks/nox $E/pkgs
cat > $E/setup.sh <<'EOF'
#!/bin/bash
E=/workspace/nox/state/p3/eval; PY=/workspace/nox/venv/bin/python; export PYTHONPATH=$E/pkgs
exec > $E/setup.log 2>&1
echo "$(date +%T) install lm_eval --no-deps"
$PY -m pip install -q --no-deps --target $E/pkgs lm_eval
for i in $(seq 1 14); do
  m=$($PY -c "import lm_eval.__main__" 2>&1 | grep -oE "No module named '[^']+'" | head -1 | sed -E "s/No module named '([^'.]+).*/\1/")
  [ -z "$m" ] && { echo "import ok"; break; }
  case $m in sklearn) pkg=scikit-learn;; yaml) pkg=pyyaml;; *) pkg=$m;; esac
  echo "missing $m -> $pkg"; $PY -m pip install -q --no-deps --target $E/pkgs $pkg 2>&1 | tail -1
done
$PY -c "import lm_eval,sys;print('lm_eval',getattr(lm_eval,'__version__','?'))" 2>&1 | tail -2
EOF
chmod +x $E/setup.sh
setsid -f $E/setup.sh > /dev/null 2>&1 < /dev/null
sleep 100; cat $E/setup.log | tail -25
