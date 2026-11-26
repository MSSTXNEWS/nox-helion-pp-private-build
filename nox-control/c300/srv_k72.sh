echo "C300: srv_k72"
cd /workspace/nox
wc -l stewards/chat_guard.py; grep -n "chat_hold\|qa-\|session\|def \|journal\|web_conv" stewards/chat_guard.py | head -40 | cut -c1-200
grep -n "chat_hold" agent/arbiter.py stewards/nox_orch.py | head -6 | cut -c1-200
ls state/web/web_conv | head -3; ls -t state/web/web_conv | head -5
