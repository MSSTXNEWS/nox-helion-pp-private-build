echo "K1: v1b_x1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/v1b; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_v1b_$cb; mkdir -p $T
for f in chat-v1b.html chat-v1c.html chat-dc.html ab/ab.js ab/ab.css ab/skin.css ab/skin.js; do [ -f $S/$f ] && { mkdir -p $T/$(dirname $f); cp -a $S/$f $T/$f; }; done; echo "backup $T"
W=/tmp/v1b_$cb; mkdir -p $W; ok=0
for k in 1 2 3 4 5 6; do rm -rf $W/*; fail=0
 for f in chat-v1b.html chat-v1c.html ab.js ab.css skin.css skin.js; do curl -fsSL "$R/$f?cb=$cb$k" -o $W/$f || fail=1; done
 [ $fail = 0 ] && grep -q nox-credfix $W/ab.js && grep -q ab/skin.js $W/chat-v1c.html && grep -q ab/ab.js $W/chat-v1b.html && grep -q arwes-frames $W/skin.js && { ok=1; break; }; sleep 5; done
[ $ok = 1 ] || { echo STALE; exit 0; }
mkdir -p $S/ab; cp $W/ab.js $W/ab.css $W/skin.css $W/skin.js $S/ab/; cp $W/chat-v1b.html $W/chat-v1c.html $S/
echo "installed credfix=$(grep -c nox-credfix $S/ab/ab.js) ab.js=$(wc -c <$S/ab/ab.js)B"
for v in gsap/gsap.min.js nox-wow/uplot/uPlot.iife.min.js nox-wow/uplot/uPlot.min.css tsparticles/tsparticles.bundle.min.js arwes-frames/arwes-frames.esm.js fonts-wow/fonts.css; do [ -f $S/vendor/$v ] && echo "vendor $v OK" || echo "vendor $v MISSING"; done
[ -f $S/assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp ] && echo "world bg OK" || echo "world bg MISSING"
bash <(curl -fsSL "$R/../th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/../th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for u in chat-v1b.html chat-v1c.html ab/ab.js ab/ab.css ab/skin.css ab/skin.js chat-dc.html vendor/gsap/gsap.min.js vendor/nox-wow/uplot/uPlot.iife.min.js vendor/tsparticles/tsparticles.bundle.min.js vendor/arwes-frames/arwes-frames.esm.js assets/nox-owner-approved/NOX_HOME_OWNER_APPROVED_WEB.webp; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
for a in api/nox-live api/nox/status api/nox/training/status stt/health memory/health; do echo "$a $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/$a)"; done
echo "nox_mem direct: $(curl -s -m 3 http://127.0.0.1:18220/health | head -c 120)"
