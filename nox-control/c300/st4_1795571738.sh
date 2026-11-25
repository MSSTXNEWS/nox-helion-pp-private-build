curl -s -o /dev/null -w "web %{http_code}\n" -m5 http://127.0.0.1:8091/web/chat.html
ss -ltn | grep -c 8091
tail -5 /workspace/nox/agent/out/web*.log 2>/dev/null | cut -c1-200
