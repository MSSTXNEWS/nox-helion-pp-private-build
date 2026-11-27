echo "K1: rs_web"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; S=$N/web/site; CF=$N/ops/web_chat_auth/Caddyfile; cb=$(date +%s)
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
T=$N/state/web_bak_rs_$cb; mkdir -p $T/ab1d; cp -a $S/ab1d/ab.js $T/ab1d/; cp -a $S/chat-dc.html $T/; cp -a $CF $T/Caddyfile
# 1) Caddy
if ! grep -q "memapi" $CF; then
python3 - <<'PY'
p="/workspace/nox/ops/web_chat_auth/Caddyfile"; s=open(p).read()
blk="\t# RS 27.11: память чата — только list и forget (POST) -> nox_mem :18220\n\t@memapi {\n\t\tmethod POST\n\t\tpath /api/nox/memory/list /api/nox/memory/forget\n\t}\n\thandle @memapi {\n\t\turi strip_prefix /api/nox/memory\n\t\treverse_proxy 127.0.0.1:18220\n\t}\n"
k="\thandle /memory/* {"; assert k in s; open(p,"w").write(s.replace(k,blk+k,1))
PY
PID=$(pgrep -f "caddy.*web_chat_auth/Caddyfile" | head -1); BIN=$(readlink /proc/$PID/exe)
if $BIN validate --config $CF --adapter caddyfile >/dev/null 2>&1; then echo caddy_valid=yes; bash <(curl -fsSL "$R/caddy_rs1.sh?cb=$cb") 2>&1 | tail -8
else echo caddy_valid=NO; cp -a $T/Caddyfile $CF; fi
else echo "caddy: already"; fi
echo "mem list via gate-less: $(curl -s -m6 -X POST -H 'Content-Type: application/json' -d '{"user":"owner","n":2}' http://127.0.0.1:18091/api/nox/memory/list | cut -c1-80 | sed 's/"text": "[^"]*"/"text":"…"/')"
echo "mem recall blocked code: $(curl -s -o /dev/null -w %{http_code} -X POST -d '{}' http://127.0.0.1:18091/api/nox/memory/recall)"
# 2) client
W=/tmp/rsw_$cb; mkdir -p $W; ok=0
for k in 1 2 3 4 5 6; do curl -fsSL "$R/bundles/v1d/ab.js?cb=$cb$k" -o $W/ab.js && grep -q __noxStop $W/ab.js && grep -q nox-credfix $W/ab.js && { ok=1; break; }; sleep 6; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $W/ab.js $S/ab1d/ab.js; cp $S/chat-v1d.html $S/chat-dc.html
bash <(curl -fsSL "$R/../th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/../th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for u in chat-dc.html chat-v1d.html ab1d/ab.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
echo "served has noxStop: $(curl -s http://127.0.0.1:18091/web/ab1d/ab.js | grep -c __noxStop)"
