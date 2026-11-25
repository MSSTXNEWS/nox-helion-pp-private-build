echo S4RUN:s4_mem1
P=/workspace/nox/web/pkg/server
grep -n "def _memory" -A25 $P/web_server.py | cut -c1-220 | head -45
R=$(find /workspace/nox /root/nox -name "recall_api*.py" -not -path "*/venv/*" 2>/dev/null | head -1); echo R=$R
grep -n "empty text\|def do_POST\|def handle\|\"op\"\|'op'\|path ==" $R | cut -c1-200 | head -40
for b in '{"op":"health"}' '{"text":"привет"}' '{"query":"проект"}' '{"op":"search","query":"проект","k":3}'; do echo "-- $b"; curl -s -m8 -X POST -H 'Content-Type: application/json' -d "$b" 127.0.0.1:8095/ | head -c 250; echo; curl -s -m8 -X POST -H 'Content-Type: application/json' -d "$b" 127.0.0.1:8091/memory/api | head -c 250; echo; done
