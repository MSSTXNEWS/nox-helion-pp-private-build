echo "C300: k_chk8"
U=https://semiconductor-valid-paintball-cancelled.trycloudflare.com
curl -s -m 10 -o /tmp/pub_chat.html -w "pub %{http_code}\n" "$U/web/chat.html?cb=$(date +%s)"
grep -o 'nox-chat-clean[^"]*' /tmp/pub_chat.html | head -3; grep -o 'nox-theme.js[^"]*' /tmp/pub_chat.html | head -1
grep -o 'nox-chat-clean[^"]*' /workspace/nox/web/site/chat.html | head -2
curl -sI -m 8 "$U/web/chat.html" | grep -iE "cache-control|etag|last-modified|cf-cache"
ls /workspace/nox/web/site/sw.js /workspace/nox/web/site/*sw*.js 2>/dev/null; grep -l "serviceWorker.register" /workspace/nox/web/site/*.js 2>/dev/null | head -3
tail -2 /workspace/nox/agent/out/web_chat_tunnel.log | cut -c1-150
