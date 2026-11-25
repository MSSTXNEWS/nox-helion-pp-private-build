echo "C300: k_noauth3"
grep -n "trycloudflare.com" /workspace/nox/agent/out/web_chat_tunnel.log | tail -5 | cut -c1-160
ls -la --time-style=+%FT%T /proc/3887718 2>/dev/null | head -1; ps -o pid,lstart,cmd -p 3887718 | cut -c1-160
curl -sI -m 10 "https://semiconductor-valid-paintball-cancelled.trycloudflare.com/web/chat.html" | grep -iE "HTTP/|www-auth|server|set-cookie" | head
