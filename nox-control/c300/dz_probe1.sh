echo "K1: dz_probe1"
G=/workspace/nox/state/owner_gate
for p in 18091 18092; do
 A=""; [ $p = 18092 ] && A="-u owner:$(cat $G/pass)"
 for u in /api/nox/agenda /web/api/nox/agenda /api/nox/self_now; do
  echo "$p $u $(curl -s -m 15 $A -o /tmp/pr.out -w '%{http_code} %{content_type} %{size_download}' http://127.0.0.1:$p$u) $(head -c 60 /tmp/pr.out | tr -d '\n' | tr -c '[:print:]' '?')"
 done
done
echo "caddy handles: $(grep -c 'handle /api/nox' /workspace/nox/ops/web_chat_auth/Caddyfile) agenda=$(grep -c 'handle /api/nox/agenda' /workspace/nox/ops/web_chat_auth/Caddyfile)"
supervisorctl status nox_api_bridge nox_web_chat_auth 2>&1 | head -3
echo "chat-dc bytes: $(wc -c < /workspace/nox/web/site/chat-dc.html) $(grep -o 'nox-dc-[a-z]*.js?v=[a-z0-9]*' /workspace/nox/web/site/chat-dc.html | tr '\n' ' ')"
