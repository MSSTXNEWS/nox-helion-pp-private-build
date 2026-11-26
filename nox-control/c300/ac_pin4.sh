echo "C300: ac_pin4"
grep -n "cpus" /workspace/nox/stewards/*.py /workspace/nox/stewards/*.json /workspace/nox/stewards/*.yaml 2>/dev/null | head -20 | cut -c1-220
tail -n 6 /workspace/nox/agent/autotrain/rounds/r037/train.log | cut -c1-200
ls /workspace/nox/agent/autotrain/rounds/r037/
grep -aE "шаг|step" /workspace/nox/agent/autotrain/rounds/r036/train.log | tail -6 | cut -c1-200
