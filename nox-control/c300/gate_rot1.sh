echo "K1: gate_rot1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; G=$N/state/owner_gate
P=$(mktemp); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/enc/owner_pub.pem?cb=$(date +%s)" -o $P
CADDY=$(readlink /proc/$(pgrep -f "$G/Caddyfile" | head -1)/exe 2>/dev/null); [ -n "$CADDY" ] || CADDY=$(command -v caddy)
cp -a $G/pass $G/pass.bak_rot; cp -a $G/Caddyfile $G/Caddyfile.bak_rot
(umask 077; openssl rand -base64 24 | tr -d '/+=' | cut -c1-20 > $G/pass)
H=$($CADDY hash-password --plaintext "$(cat $G/pass)")
python3 - "$G/Caddyfile" "$H" <<'PY'
import sys,re
f,h=sys.argv[1],sys.argv[2]; t=open(f).read()
t=re.sub(r'(owner\s+)\S+', lambda m: m.group(1)+h, t, count=1); open(f,'w').write(t)
PY
chmod 600 $G/Caddyfile
pkill -f "$G/Caddyfile"; sleep 1
setsid -f $CADDY run --config $G/Caddyfile --adapter caddyfile >$G/caddy.log 2>&1 </dev/null
sleep 3
echo "noauth=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:18092/web/chat-dc.html) newauth=$(curl -s -o /dev/null -m 5 -w %{http_code} -u owner:$(cat $G/pass) http://127.0.0.1:18092/web/chat-dc.html) oldauth=$(curl -s -o /dev/null -m 5 -w %{http_code} -u owner:$(cat $G/pass.bak_rot) http://127.0.0.1:18092/web/chat-dc.html)"
shred -u $G/pass.bak_rot 2>/dev/null || rm -f $G/pass.bak_rot
cat $G/pass | openssl pkeyutl -encrypt -pubin -inkey $P | base64 -w0; echo; rm -f $P
