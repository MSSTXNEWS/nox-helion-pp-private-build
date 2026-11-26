echo "K1: jv_x1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_jv1_$cb; mkdir -p $T
cp -a $S/chat-dc.html $T/ && cp -a $S/chat-dc.html $S/chat-dc-old.html; echo "backup $T"
for v in vendor/three/build/three.module.js vendor/echarts/echarts.min.js vendor/gsap/gsap.min.js vendor/deep-chat/deep-chat.iife.js vendor/nox-fx/hud.js vendor/fonts-wow/fonts.css; do [ -f $S/$v ] && echo "ok $v" || echo "MISSING $v"; done
for f in nox-jarvis.css nox-jarvis.js nox-jarvis-core.js; do curl -fsSL "$R/jv1/$f?cb=$cb" -o $S/$f || echo "FAIL $f"; done
curl -fsSL "$R/jv1/concept-c.html?cb=$cb" -o /tmp/jv.html && cp /tmp/jv.html $S/chat-jarvis.html && cp /tmp/jv.html $S/chat-dc.html
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
grep -c "nox-jarvis" $S/chat-dc.html
for p in chat-dc chat-jarvis chat-dc-old nox-jarvis.js nox-jarvis-core.js nox-jarvis.css; do case $p in *.js|*.css) u=$p;; *) u=$p.html;; esac; echo "$p $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/web/$u)"; done
for a in api/nox-live api/nox/agenda api/nox/status; do echo "$a $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/$a)"; done
