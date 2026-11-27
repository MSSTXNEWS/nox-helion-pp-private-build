export RUNNER_TRACKING_ID=""
echo "C300: tr_cad4"
CF=/workspace/nox/ops/web_chat_auth/Caddyfile; CB=/opt/portal-aio/caddy_manager/.mptcp_off/caddy
sed -n 6,10p $CF | sed -E 's/(hash|token|secret|password|key)[^ ]* +[^ ]+/\1 REDACTED/Ig' | cut -c1-120
cp -n $CF $CF.bak_tr_20261127
if grep -q "api/nox/memory/health" $CF; then echo "уже есть"; else
python3 - <<'PY'
p="/workspace/nox/ops/web_chat_auth/Caddyfile"; s=open(p).read()
key="\thandle /memory/* {"
assert s.count(key)==1
add="\t# TR 27.11: health памяти nox_mem :18220 (только /health, без записи/чтения фактов)\n\thandle /api/nox/memory/health {\n\t\trewrite * /health\n\t\treverse_proxy 127.0.0.1:18220\n\t}\n"
open(p,"w").write(s.replace(key,add+key)); print("вставлено")
PY
fi
$CB validate --config $CF --adapter caddyfile 2>&1 | tail -2
if $CB validate --config $CF --adapter caddyfile >/dev/null 2>&1; then
  $CB reload --config $CF --adapter caddyfile 2>&1 | tail -2; sleep 3
else echo "валидация провалена — откат"; cp $CF.bak_tr_20261127 $CF; fi
for u in /api/nox/memory/health /memory/health /api/health; do echo "$u -> $(curl -s -m5 -w ' [%{http_code}]' http://127.0.0.1:18091$u | head -c 150)"; done
echo END
