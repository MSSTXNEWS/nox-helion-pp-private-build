echo "K1: gate_set2"
# Владелец 28.11 14:55 МСК: сменить пароль входа (значение передано шифрованно).
export RUNNER_TRACKING_ID=""
N=/workspace/nox; G=$N/state/owner_gate; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles
NEWP=$(curl -fsSL $R/enc_in/gp1.b64 | base64 -d | openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem) || { echo DECRYPT_FAIL; exit 0; }
[ ${#NEWP} -ge 6 ] || { echo BAD_PASS; exit 0; }
CADDY=$(readlink /proc/$(pgrep -f "$G/Caddyfile" | head -1)/exe 2>/dev/null); [ -n "$CADDY" ] || CADDY=$(command -v caddy)
cp -a $G/pass $G/pass.bak_set2; cp -a $G/Caddyfile $G/Caddyfile.bak_set2
(umask 077; printf '%s' "$NEWP" > $G/pass)
H=$($CADDY hash-password --plaintext "$NEWP")
python3 - "$G/Caddyfile" "$H" <<'PY'
import sys,re
f,h=sys.argv[1],sys.argv[2]; t=open(f).read()
t=re.sub(r'(owner\s+)\S+', lambda m: m.group(1)+h, t, count=1); open(f,'w').write(t)
PY
chmod 600 $G/Caddyfile
if ! $CADDY validate --config $G/Caddyfile --adapter caddyfile >/dev/null 2>&1; then echo "invalid -> restore"; cp -a $G/Caddyfile.bak_set2 $G/Caddyfile; cp -a $G/pass.bak_set2 $G/pass; exit 0; fi
pkill -f "$G/Caddyfile"; sleep 1
setsid -f $CADDY run --config $G/Caddyfile --adapter caddyfile >$G/caddy.log 2>&1 </dev/null
sleep 3
echo "noauth=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:18092/web/index.html) newauth=$(curl -s -o /dev/null -m 5 -w %{http_code} -u owner:$(cat $G/pass) http://127.0.0.1:18092/web/index.html) oldauth=$(curl -s -o /dev/null -m 5 -w %{http_code} -u owner:$(cat $G/pass.bak_set2) http://127.0.0.1:18092/web/index.html)"
shred -u $G/pass.bak_set2 2>/dev/null || rm -f $G/pass.bak_set2
echo END
