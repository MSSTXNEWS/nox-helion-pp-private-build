echo "K1: k1_url2"
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/enc/owner_pub.pem?cb=$(date +%s)" -o $P
U=$(grep -rhoE "https://[a-z0-9-]+\.trycloudflare\.com" /workspace/nox/logs /workspace/nox/state 2>/dev/null | tail -1)
C=""; [ -n "$U" ] && C=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$U/web/chat-dc.html")
echo "found=$([ -n "$U" ] && echo yes || echo no) http=$C cloudflared=$(pgrep -c cloudflared)"
printf '%s' "$U" | openssl pkeyutl -encrypt -pubin -inkey $P | base64 -w0; echo; rm -f $P
