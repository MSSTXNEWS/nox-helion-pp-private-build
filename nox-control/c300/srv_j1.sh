P=$(pgrep -f "uvicorn judge_service" | head -1); echo pid $P ppid=$(ps -o ppid= -p $P) et=$(ps -o etimes= -p $P)
tr '\0' ' ' </proc/$P/cmdline; echo; PP=$(ps -o ppid= -p $P | tr -d ' '); tr '\0' ' ' </proc/$PP/cmdline | cut -c1-150; echo
tr '\0' '\n' </proc/$P/environ | grep -E "^NOX_|^CUDA|^OMP|^PYTHONPATH|^HF_" | sed -E 's/(KEY|TOKEN)=.*/\1=***/'
grep -rn "uvicorn judge_service\|judge_service" /workspace/nox/ops/*.sh /workspace/nox/stewards/*.sh /workspace/nox/agent/*.sh /etc/supervisor/conf.d/*.conf 2>/dev/null | grep -v bak | head -5 | cut -c1-200
grep -n "def _train_phase" -A8 /workspace/nox/judges/judge_service.py | cut -c1-170
