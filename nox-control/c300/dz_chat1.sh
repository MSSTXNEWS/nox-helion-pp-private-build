echo "K1: dz_chat1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_dz1_$cb; mkdir -p $T
for f in chat-dc.html nox-dc-fill.js nox-dc-agenda.js nox-dc-wow.js nox-dc-wow.css; do [ -f $S/$f ] && cp -a $S/$f $T/; done; echo "backup $T ($(ls $T|wc -l) files)"
for f in nox-fx.js nox-fx.css nox-worlds.js nox-worlds.css nox-reveal.js vendor/fx/gsap.min.js vendor/fx/motion.js vendor/nox-extra/tsparticles.slim.bundle.min.js; do [ -f $S/$f ] && echo "have $f" || echo "MISSING $f"; done
ok=0; for k in 1 2 3 4 5 6; do t=$(date +%s)$k
 for f in nox-dc-wow.css nox-dc-wow.js nox-dc-fill.js nox-dc-agenda.js patch.py; do curl -fsSL "$R/dz_chat1/$f?cb=$t" -o /tmp/dz_$f; done
 grep -q 'nxw-aurora' /tmp/dz_nox-dc-wow.css && grep -q 'NOXdcWow' /tmp/dz_nox-dc-wow.js && grep -q '__nxFill' /tmp/dz_nox-dc-fill.js && grep -q '__nxFill' /tmp/dz_nox-dc-agenda.js && grep -q 'patched' /tmp/dz_patch.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
for f in nox-dc-wow.css nox-dc-wow.js nox-dc-fill.js nox-dc-agenda.js; do cp /tmp/dz_$f $S/$f; done
python3 /tmp/dz_patch.py $S
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for u in chat-dc.html nox-dc-wow.js nox-dc-wow.css nox-fx.js nox-worlds.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/web/$u)"; done
echo "agenda $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/api/nox/agenda)"; grep -c 'nox-dc-wow' $S/chat-dc.html
