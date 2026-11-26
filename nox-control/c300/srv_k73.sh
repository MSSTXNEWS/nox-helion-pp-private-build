echo "C300: srv_k73"
cat /workspace/nox/stewards/chat_guard.py | cut -c1-260
ps -o pid,etimes,args -p 3989795 | cut -c1-150; cat /proc/3989795/environ | tr '\0' '\n' | grep -E "^NOX_|^PATH" | head -3
grep -rn "chat_guard" /workspace/nox/stewards/*.sh /workspace/nox/agent/*.sh /etc/supervisor/conf.d/*.conf 2>/dev/null | head -4 | cut -c1-200
