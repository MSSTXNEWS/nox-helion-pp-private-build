echo "C300: k_noauth4"
date -u > /workspace/nox/state/web_auth_off && echo "switch on"
sleep 2
curl -s -m 10 -o /dev/null -w "public %{http_code}\n" "https://semiconductor-valid-paintball-cancelled.trycloudflare.com/web/chat.html?z=1"
