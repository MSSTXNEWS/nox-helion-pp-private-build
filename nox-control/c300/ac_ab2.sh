echo "C300: ac_ab2"
D=/workspace/nox/tmp/ab
setsid -f bash $D/ab.sh </dev/null >$D/ab.log 2>&1
P=/workspace/nox/vendor/NOX_V7_CORE_PACKAGE_20261123/nox_wow/prompt_cache_patch.py
wc -l $P; sed -n 1,40p $P | cut -c1-200
grep -lE "8104" /workspace/nox/*.py /workspace/nox/brain/*.py /workspace/nox/web/*.py /workspace/nox/agent/*.py 2>/dev/null | head -8
grep -n "prompt_cache_patch" -r /workspace/nox/brain /workspace/nox/web --include=*.py -s 2>/dev/null | head -5 | cut -c1-200
sleep 200; cat $D/res.txt
