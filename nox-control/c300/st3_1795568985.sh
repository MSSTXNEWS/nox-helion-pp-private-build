curl -s -o /dev/null -w "web %{http_code}\n" -m5 http://127.0.0.1:8091/web/chat.html
curl -s -m8 http://127.0.0.1:8091/api/chat/health | head -c 200; echo
