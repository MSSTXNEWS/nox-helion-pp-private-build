#!/bin/bash
E=/workspace/nox/state/p3/eval; PY=/workspace/nox/venv/bin/python
$PY -m pip install -q --no-deps --target $E/pkgs tenacity aiohttp requests tqdm 2>&1 | tail -2
cat > $E/go.sh <<'EOF'
#!/bin/bash
E=/workspace/nox/state/p3/eval
$E/run_eval.sh base
EOF
chmod +x $E/go.sh; setsid -f $E/go.sh > /dev/null 2>&1 < /dev/null
sleep 150; tail -12 $E/run_base.log | cut -c1-220
