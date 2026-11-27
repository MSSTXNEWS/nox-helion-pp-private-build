echo "K1: jv_l3p2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; cb=$(date +%s)
S=/workspace/nox/web/site; T=/workspace/nox/state/web_bak_jv_l3p2_$cb; mkdir -p $T
for f in nox-jarvis.js nox-jarvis.css cinema.html connections.html consciousness.html constructor.html contacts.html creative.html dispatcher.html downloads.html effects.html evolution.html  ; do [ -f $S/$f ] && cp -a $S/$f $T/; done; echo "backup $T ($(ls $T|wc -l) files)"
for v in vendor/echarts/echarts.min.js vendor/gsap/gsap.min.js; do [ -f $S/$v ] && echo "ok $v" || echo "MISSING $v"; done
ok=0; for k in 1 2 3 4 5 6; do t=$(date +%s)$k
 for f in nox-jarvis-layer.js nox-jarvis-layer.css nox-jarvis.js patch.py; do curl -fsSL "$R/jv3/$f?cb=$t" -o /tmp/jv3_$f; done
 grep -q 'noxJvLayer' /tmp/jv3_nox-jarvis-layer.js && grep -q 'jv-hudrow' /tmp/jv3_nox-jarvis-layer.css && grep -q 'hasOwnProperty' /tmp/jv3_nox-jarvis-layer.js && grep -q 'ram_used_pct' /tmp/jv3_nox-jarvis.js && grep -q tagged /tmp/jv3_patch.py && { ok=1; break; }; sleep 5; done
[ $ok = 1 ] || { echo STALE; exit 0; }
for f in nox-jarvis-layer.js nox-jarvis-layer.css nox-jarvis.js; do cp /tmp/jv3_$f $S/$f; done
python3 /tmp/jv3_patch.py $S cinema connections consciousness constructor contacts creative dispatcher downloads effects evolution
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for p in cinema connections consciousness constructor contacts creative dispatcher downloads effects evolution ; do echo "$p $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/web/$p.html) tag=$(curl -s http://127.0.0.1:18091/web/$p.html | grep -c nox-jarvis-layer)"; done
for u in nox-jarvis-layer.js nox-jarvis-layer.css nox-jarvis.js vendor/echarts/echarts.min.js; do echo "$u $(curl -s -o /dev/null -w '%{http_code} %{size_download}' http://127.0.0.1:18091/web/$u)"; done
for a in api/nox-live api/nox/agenda api/nox/status api/nox/training/status api/pc-metrics glm/props; do echo "$a $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/$a)"; done
echo "chat-dc $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:18091/web/chat-dc.html)"
