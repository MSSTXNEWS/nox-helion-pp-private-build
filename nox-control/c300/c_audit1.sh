#!/bin/bash
# c_audit1: запуск ревизора на chat, index, consciousness, organism в фоне (не более одного экземпляра)
N=/workspace/nox; LOG=$N/state/c_audit1.log
if pgrep -f "qa_audit.py" >/dev/null; then echo "already running"; pgrep -af qa_audit.py | head -2; exit 0; fi
cd $N && setsid nohup /workspace/nox/venv/bin/python -I $N/qa_audit.py chat.html index.html consciousness.html organism.html > $LOG 2>&1 < /dev/null &
sleep 5; echo "started"; pgrep -af qa_audit.py | head -2; echo "LOG HEAD:"; head -c 500 $LOG
