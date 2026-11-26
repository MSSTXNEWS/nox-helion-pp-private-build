echo "K1: k1_gate1"
set -u
N=/workspace/nox; G=$N/state/owner_gate; mkdir -p $G; chmod 700 $G
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/enc/owner_pub.pem?cb=$(date +%s)" -o $P
CADDY=$(command -v caddy || ls $N/tools/caddy* /usr/local/bin/caddy /usr/bin/caddy 2>/dev/null | head -1)
CF=$(command -v cloudflared || ls $N/tools/cloudflared* /usr/local/bin/cloudflared 2>/dev/null | head -1)
echo "caddy=$([ -n "$CADDY" ] && echo ok || echo MISSING) cf=$([ -n "$CF" ] && echo ok || echo MISSING)"
[ -n "$CADDY" ] && [ -n "$CF" ] || exit 1
[ -f $G/pass ] || (umask 077; openssl rand -base64 18 | tr -d '/+=' | cut -c1-16 > $G/pass)
H=$($CADDY hash-password --plaintext "$(cat $G/pass)")
umask 077; cat > $G/Caddyfile <<C
{
	admin off
}
:18092 {
	bind 127.0.0.1
	basicauth {
		owner $H
	}
	reverse_proxy 127.0.0.1:18091 {
		flush_interval -1
	}
}
C
pkill -f "$G/Caddyfile" 2>/dev/null; pkill -f "metrics 127.0.0.1:20999" 2>/dev/null; sleep 1
setsid -f $CADDY run --config $G/Caddyfile --adapter caddyfile >$G/caddy.log 2>&1 </dev/null
sleep 2; echo "gate_noauth=$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:18092/web/chat-dc.html) gate_auth=$(curl -s -o /dev/null -m 5 -w '%{http_code}' -u owner:$(cat $G/pass) http://127.0.0.1:18092/web/chat-dc.html)"
setsid -f $CF tunnel --no-autoupdate --metrics 127.0.0.1:20999 --url http://127.0.0.1:18092 >$G/cf.log 2>&1 </dev/null
U=""; for i in $(seq 1 30); do U=$(curl -s -m 2 http://127.0.0.1:20999/quicktunnel | grep -oE '"hostname":"[^"]+"' | cut -d'"' -f4); [ -n "$U" ] && break; sleep 2; done
sleep 10; echo "tunnel=$([ -n "$U" ] && echo yes || echo no) pub_noauth=$(curl -s -o /dev/null -m 15 -w '%{http_code}' https://$U/web/chat-dc.html) pub_auth=$(curl -s -o /dev/null -m 15 -w '%{http_code}' -u owner:$(cat $G/pass) https://$U/web/chat-dc.html)"
printf '%s %s' "$U" "$(cat $G/pass)" | openssl pkeyutl -encrypt -pubin -inkey $P | base64 -w0; echo; rm -f $P
