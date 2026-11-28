echo "K1: sc1"
# Владелец одобрил 28.11 ~04:10 МСК: автозапуск 5 служб + маршруты Caddy с проверкой и автооткатом.
export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles; ts=$(date +%s)
W=$(mktemp -d); curl -fsSL $R/enc_in/sc1.enc -o $W/e; curl -fsSL $R/enc_in/sc1.key -o $W/k
openssl pkeyutl -decrypt -inkey $N/state/keys/inbox.pem -in $W/k -out $W/kk && openssl enc -d -aes-256-cbc -pbkdf2 -in $W/e -pass file:$W/kk | tar xzf - -C $W || { echo DECRYPT_FAIL; exit 0; }
mkdir -p $N/mods $N/logs; cp $W/mods/* $N/mods/
WP=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/')
WS=$(tr '\0' '\n' < /proc/$WP/environ 2>/dev/null | sed -n 's/^NOX_WEB_STATE=//p'); NS=$(tr '\0' '\n' < /proc/$WP/environ 2>/dev/null | sed -n 's/^NOX_STATE=//p')
[ -z "$WS" ] && WS=${NS:-/root/nox/state}/web
echo "web_state_has_conv=$(ls $WS 2>/dev/null | grep -c conv)"
sed -i "s#NOX_WEB_STATE=\"[^\"]*\"#NOX_WEB_STATE=\"$WS\"#" $W/sup/nox_sidecar.conf
CD=$(grep -lr "program:nox_mem" /etc/supervisor /etc/supervisord* $N/ops 2>/dev/null | head -1 | xargs -r dirname)
echo "conf_dir_found=$([ -n "$CD" ] && echo yes || echo no)"
[ -n "$CD" ] || { echo ABORT; rm -rf $W; exit 0; }
for f in $W/sup/*.conf; do cp $f $CD/; done
supervisorctl reread >/dev/null 2>&1; supervisorctl update 2>&1 | grep -oE "nox_[a-z_]+: [a-z ]+" | sort | uniq
sleep 6; for p in nox_sidecar nox_voice nox_inspector nox_weekly_exam nox_sensorium_ext; do echo "sv $p $(supervisorctl status $p 2>/dev/null | awk '{print $2}')"; done
CF=$N/ops/web_chat_auth/Caddyfile; cp -a $CF $CF.bak_sc1_$ts
if ! grep -q NOX_SIDECAR $CF; then python3 - $CF $W/caddy_routes.snippet <<'PY'
import sys,re
cf,sn=sys.argv[1],sys.argv[2]; L=open(cf).read().split("\n"); S=["\t# NOX_SIDECAR"]+[l for l in open(sn).read().split("\n") if not l.startswith("#")]
i=next((k for k,l in enumerate(L) if re.search(r"handle\s+/api/nox/memory",l)),None)
if i is None: i=next((k for k,l in enumerate(L) if re.match(r"\s*handle\b",l)),None)
if i is None: i=next((k for k,l in enumerate(L) if re.search(r"reverse_proxy\s+127\.0\.0\.1:8091",l)),None)
if i is None: print("NO_ANCHOR"); sys.exit(0)
open(cf,"w").write("\n".join(L[:i]+S+L[i:])); print("inserted_at_line",i)
PY
fi
PID=$(pgrep -f "caddy.*web_chat_auth/Caddyfile" | head -1); BIN=$(readlink /proc/$PID/exe)
if $BIN validate --config $CF --adapter caddyfile >/dev/null 2>&1; then echo valid=yes
  SV=$(supervisorctl status 2>/dev/null | awk '{print $1}' | while read p; do supervisorctl pid $p 2>/dev/null | grep -qx "$PID" && echo $p; done | head -1)
  [ -n "$SV" ] && supervisorctl restart $SV >/dev/null 2>&1 && echo caddy_restarted || echo caddy_not_supervised
else echo "valid=no -> restore"; cp -a $CF.bak_sc1_$ts $CF; fi
sleep 3
for u in "/api/convs?user=owner" "/api/context?conversation_id=x" "/api/memory/graph?user=owner" "/voice/health" "/web/chat-dc.html" "/api/nox/status"; do echo "route $u $(curl -s -o /dev/null -m 8 -w %{http_code} "http://127.0.0.1:18091$u")"; done
echo "draft $(curl -s -o /dev/null -m 8 -w %{http_code} -X POST -H 'Content-Type: application/json' -d '{"conversation_id":"qa-x","prefix":"Привет, как"}' http://127.0.0.1:18091/api/draft)"
echo "tts $(curl -s -m 20 -o /tmp/t.wav -w '%{http_code} %{size_download}' -X POST -H 'Content-Type: application/json' -d '{"text":"Привет, Создатель."}' http://127.0.0.1:18091/api/tts)"
echo "sidecar_direct $(curl -s -o /dev/null -m 4 -w %{http_code} http://127.0.0.1:18798/health) voice_direct $(curl -s -o /dev/null -m 4 -w %{http_code} http://127.0.0.1:18797/health)"
echo "gate $(curl -s -o /dev/null -m 8 -w %{http_code} -u owner:$(cat $N/state/owner_gate/pass) http://127.0.0.1:18092/web/chat-dc.html)"
rm -rf $W; echo END
