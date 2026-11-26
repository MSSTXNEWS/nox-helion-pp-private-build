echo "C300: srv_k157"
date -u +%T; timeout 60 python3 /tmp/k1p2.py "Привет, NOX! Как дела?"
tail -n 3 /workspace/nox/state/chat_fast.log
