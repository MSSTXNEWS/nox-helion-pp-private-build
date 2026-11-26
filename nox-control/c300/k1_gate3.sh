echo "C300: k1_gate3"
N=/workspace/nox; G=$N/state/owner_gate
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/enc/owner_pub.pem?cb=$(date +%s)" -o $P
CADDY=$(command -v caddy || ls $N/tools/caddy* /usr/local/bin/caddy /usr/bin/caddy 2>/dev/null | head -1)
CF=$(command -v cloudflared || ls $N/tools/cloudflared* /usr/local/bin/cloudflared 2>/dev/null | head -1)
pkill -f "$G/Caddyfile" 2>/dev/null; pkill -f "metrics 127.0.0.1:20999" 2>/dev/null; sleep 1
setsid -f $CADDY run --config $G/Caddyfile --adapter caddyfile >$G/caddy.log 2>&1 </dev/null
setsid -f $CF tunnel --no-autoupdate --metrics 127.0.0.1:20999 --url http://127.0.0.1:18092 >$G/cf.log 2>&1 </dev/null
U=""; for i in $(seq 1 30); do U=$(curl -s -m 2 http://127.0.0.1:20999/quicktunnel | grep -oE '"hostname":"[^"]+"' | cut -d'"' -f4); [ -n "$U" ] && break; sleep 2; done
sleep 12; echo "pub_noauth=$(curl -s -o /dev/null -m 15 -w '%{http_code}' https://$U/web/chat-dc.html) pub_auth=$(curl -s -o /dev/null -m 15 -w '%{http_code}' -u owner:$(cat $G/pass) https://$U/web/chat-dc.html)"
printf '%s' "$U" | openssl pkeyutl -encrypt -pubin -inkey $P | base64 -w0; echo; rm -f $P
