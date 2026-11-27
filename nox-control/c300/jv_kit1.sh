echo "K1: jv_kit1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/jvkit; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_jvkit1_$cb; mkdir -p $T
for f in nox-jarvis.js nox-jarvis-kit.js nox-jarvis-kit.css jv-kit.html chat-dc.html vendor/INDEX.json; do [ -f $S/$f ] && { mkdir -p $T/$(dirname $f); cp -a $S/$f $T/$f; }; done; echo "backup $T"
echo "server nox-jarvis.js: $(wc -c <$S/nox-jarvis.js) B credfix=$(grep -c nox-credfix $S/nox-jarvis.js)"
W=/tmp/jvkit_$cb; mkdir -p $W; ok=0
for k in 1 2 3 4 5 6; do rm -rf $W/*; fail=0
 for f in nox-jarvis.js nox-jarvis-kit.js nox-jarvis-kit.css jv-kit.html chat-dc.html vendor/INDEX.json vendor/arwes-animated/LICENSE vendor/arwes-animated/arwes-animated.esm.js vendor/arwes-animated/arwes-animated.iife.js vendor/arwes-frames/LICENSE vendor/arwes-frames/arwes-frames.esm.js vendor/arwes-frames/arwes-frames.iife.js vendor/arwes-text/LICENSE vendor/arwes-text/arwes-text.esm.js vendor/arwes-text/arwes-text.iife.js vendor/three-new/build/three.core.js vendor/three-new/build/three.module.js ; do mkdir -p $W/$(dirname $f); curl -fsSL "$R/$f?cb=$cb$k" -o $W/$f || fail=1; done
 [ $fail = 0 ] && grep -q nox-credfix $W/nox-jarvis.js && grep -q ram_used_pct $W/nox-jarvis.js && grep -q J.ring $W/nox-jarvis-kit.js && grep -q three-new $W/chat-dc.html && grep -q three.core $W/vendor/three-new/build/three.module.js && { ok=1; break; }; sleep 5; done
[ $ok = 1 ] || { echo STALE; exit 0; }
for f in nox-jarvis.js nox-jarvis-kit.js nox-jarvis-kit.css jv-kit.html chat-dc.html; do cp $W/$f $S/$f; done
for d in arwes-frames arwes-text arwes-animated three-new; do mkdir -p $S/vendor/$d; cp -r $W/vendor/$d/. $S/vendor/$d/; done; cp $W/vendor/INDEX.json $S/vendor/INDEX.json
echo "installed credfix=$(grep -c nox-credfix $S/nox-jarvis.js) three-new=$(ls $S/vendor/three-new)"
bash <(curl -fsSL "$R/../th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/../th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for u in chat-dc.html jv-kit.html nox-jarvis.js nox-jarvis-kit.js nox-jarvis-kit.css vendor/arwes-frames/arwes-frames.esm.js vendor/arwes-text vendor/arwes-animated vendor/three-new/build/three.module.js vendor/three-new/build/three.core.js vendor/INDEX.json vendor/echarts/echarts.min.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
for a in api/nox-live api/nox/agenda api/nox/status; do echo "$a $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/$a)"; done
echo "layer-page system $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/web/system.html)"
