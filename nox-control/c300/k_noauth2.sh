echo "C300: k_noauth2"
pgrep -af "caddy run" | cut -c1-140
for i in 1 2 3; do curl -s -m 10 -o /dev/null -w "public %{http_code}\n" "https://semiconductor-valid-paintball-cancelled.trycloudflare.com/web/chat.html?x=$i"; sleep 3; done
curl -s -m 8 -o /dev/null -w "local %{http_code}\n" http://127.0.0.1:18091/web/chat.html
tail -3 /workspace/nox/agent/out/web_chat_tunnel.log | cut -c1-200
