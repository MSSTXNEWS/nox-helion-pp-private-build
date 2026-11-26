echo "C300: ac_swap2"
grep -n "8812\|8811" /workspace/nox/serve/llama-swap.yaml | head; 
for p in $(pgrep -f "port 8812"); do echo "pid $p ppid $(ps -o ppid= -p $p) etimes $(ps -o etimes= -p $p)"; ps -o pid,args -p $(ps -o ppid= -p $p) | tail -1 | cut -c1-200; done
grep -rn "8812" /etc/supervisor/conf.d/ /workspace/nox/ops/*.sh /workspace/nox/stewards/*.sh /workspace/nox/serve/*.sh 2>/dev/null | head -6 | cut -c1-220
grep -n -B2 -A12 "8812" /workspace/nox/serve/llama-swap.yaml | head -30
ps -eo pid,pcpu,args --sort=-pcpu | head -5 | cut -c1-150
