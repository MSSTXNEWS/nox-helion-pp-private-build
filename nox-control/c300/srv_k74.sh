echo "C300: srv_k74"
for p in 611127 3854693 61642 523234 1352794 1903633; do echo "-- $p"; ps -o pid,ppid,etimes,args -p $p | tail -1 | cut -c1-200; echo "cwd=$(readlink /proc/$p/cwd)"; ps -o args= -p $(ps -o ppid= -p $p | tr -d ' ') | cut -c1-120; done
crontab -l 2>/dev/null | grep -v "^#" | cut -c1-160 | head -30
cat /workspace/nox/agent/autotrain/donor_hybrid.cmd | tr '\n' ' ' | cut -c1-600; echo
grep -n "def chat_active" -A25 /workspace/nox/stewards/nox_orch.py | cut -c1-200 | head -40
