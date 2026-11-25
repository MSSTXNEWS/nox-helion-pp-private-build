cd /workspace/nox/web/pkg/server
grep -n "def running_turn\|def stop\|def start_turn\|def run_turn\|уже идёт\|_RUN\|threading\|def _worker\|last_tok\|inflight\|time.time()" chat_core.py | cut -c1-200 | head -50
echo ==; grep -n "def running_turn" -A14 chat_core.py | cut -c1-220
echo ==; grep -n "def stop" -A22 chat_core.py | cut -c1-220
echo ==; grep -n "уже идёт" -B6 -A3 chat_core.py web_server.py | cut -c1-240
