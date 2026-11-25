echo S4RUN:s4_mem3
R=$(find /workspace/nox /root/nox -name "recall_server.py" -not -path "*/venv/*" 2>/dev/null | head -3); echo R=$R
ps aux | grep -i "recall\|tts2" | grep -v grep | cut -c1-200
for f in $R; do echo "== $f"; grep -n "PORT\|8095\|argv\|environ\|empty text\|\"op\"" $f | head -20 | cut -c1-180; done
cat /workspace/nox/web/pkg/server/run_web.sh | head -20
ss -ltn | awk '{print $4}' | grep -o '[0-9]*$' | sort -n | tr '\n' ' '
grep -rn "8095" /workspace/nox --include=*.sh --include=*.py --include=*.json -l 2>/dev/null | grep -v "venv\|node_modules\|bak" | head -10
