echo "C300: k_noauth1"
D=/workspace/nox/ops/web_chat_auth; F=$D/Caddyfile; TS=$(date +%s)
cp $F $F.bak_noauth_$TS && echo "backup $F.bak_noauth_$TS"
echo "--- structure (secrets masked)"; sed -E 's/\$2[aby]\$[^ ]+/***HASH***/; s/(password|token|secret)[^ ]*\s+\S+/\1 ***/I' $F | head -40
python3 - "$F" <<'PY'
import sys,re
p=sys.argv[1]; s=open(p).read()
out=[];i=0;lines=s.split('\n');skip=0
for ln in lines:
    t=ln.strip()
    if skip:
        skip+=t.count('{')-t.count('}')
        continue
    if re.match(r'^(basicauth|basic_auth)\b',t) or re.match(r'^@?\w*auth\w*\s',t) and '{' in t and 'forward' not in t:
        skip=t.count('{')-t.count('}')
        if skip<=0: skip=0
        continue
    out.append(ln)
open(p,'w').write('\n'.join(out))
PY
echo "--- after"; sed -E 's/\$2[aby]\$[^ ]+/***HASH***/' $F | head -40
CADDY=/opt/portal-aio/caddy_manager/.mptcp_off/caddy
$CADDY validate --config $F --adapter caddyfile 2>&1 | tail -2 || { cp $F.bak_noauth_$TS $F; echo ROLLBACK; exit 1; }
OLD=$(pgrep -f "caddy run --config $F")
kill $OLD; sleep 1
setsid nohup $CADDY run --config $F --adapter caddyfile >> /workspace/nox/agent/out/web_chat_caddy.log 2>&1 </dev/null &
sleep 3
curl -s -m 8 -o /dev/null -w "local18091 %{http_code}\n" http://127.0.0.1:18091/web/chat.html
curl -s -m 10 -o /dev/null -w "public %{http_code}\n" https://semiconductor-valid-paintball-cancelled.trycloudflare.com/web/chat.html
