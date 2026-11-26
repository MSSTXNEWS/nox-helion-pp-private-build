echo "C300: ac_reg2"
grep -rnE "taskset|sched_setaffinity" /workspace/nox/ops/*.py /workspace/nox/ops/*.sh /workspace/nox/stewards/*.py /workspace/nox/stewards/*.sh /workspace/nox/agent/*.py /workspace/nox/agent/autotrain/*.sh 2>/dev/null | grep -v "^.*bak" | cut -c1-210 | head -30
grep -n "EMBED_CPUS *=" /workspace/nox/stewards/chat_guard.py
