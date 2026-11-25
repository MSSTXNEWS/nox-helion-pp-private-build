#!/bin/bash
echo "C300: p2_web_diag2"; date -u
D=/workspace/nox/web/pkg/server; PY=/workspace/nox/venv/bin/python
echo "## web_server.log tail"; tail -40 /workspace/nox/agent/out/web_server.log 2>/dev/null | cut -c1-240
echo "## n_web_restart.log"; tail -20 /tmp/n_web_restart.log 2>/dev/null | cut -c1-240
echo "## files"; ls -la --time-style=long-iso $D | grep -E 'chat_core|web_server|run_web|\.bak' | cut -c1-160 | tail -30
echo "## compile all .py in server"; for f in $D/*.py; do $PY -m py_compile "$f" 2>&1 | tail -2 | sed "s|^|$(basename $f): |"; done; echo compiled
echo "## import test"; (cd $D && timeout 60 $PY -c "import chat_core; print('chat_core import OK')" 2>&1 | tail -12 | cut -c1-240)
echo "## diff chat_core vs bak_n_2 (stat)"; for b in $D/chat_core.py.bak_n_2 $D/chat_core.py.bak_n_1; do [ -f $b ] && { cmp -s $b $D/chat_core.py && echo "$(basename $b) == current" || echo "$(basename $b) DIFFERS: $(diff $b $D/chat_core.py | wc -l) lines"; }; done
echo "## run_web.sh"; sed -n 1,50p $D/run_web.sh | cut -c1-200
echo "## DONE"
