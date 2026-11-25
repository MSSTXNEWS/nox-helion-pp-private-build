echo "C300: k8_probe_1"
S=/workspace/nox/web/site; cd $S
export PATH=/workspace/nox/tools/node/bin:$PATH
ls -la vendor/fuse.js vendor/embla-carousel | head; wc -c vendor/fuse.js/* vendor/embla-carousel/*
cat vendor/fuse.js/*.json 2>/dev/null | head -5
echo ---K7FIND; cat nox-k7-find.js | head -c 5500; echo
echo ---K7CARDS; grep -n "k7-snap\|scroll" nox-k7-cards.js | head -5
echo ---EMBLA_USERS; grep -l "embla" nox-k*.js | head; grep -l "fuse" nox-k*.js | head
for p in finance atlas system organism training projects growth cinema consciousness settings knowledge board; do echo "--PG $p"; [ -f $p.html ] && { wc -c $p.html; grep -o '<script[^>]*src="[^"]*"' $p.html | sed 's/<script[^>]*src=//' | tr '\n' ' ' | head -c 700; echo; grep -o 'id="[^"]*"' $p.html | head -50 | tr '\n' ' '; echo; }; done
ls data | tr '\n' ' '; echo
ls vendor/echarts vendor/ts-fsrs vendor/d3-shape vendor/sortablejs vendor/suncalc vendor/maplibre-gl 2>&1 | head -40
(rm -rf /tmp/k8n; mkdir /tmp/k8n; cd /tmp/k8n; timeout 100 npm view fuse.js version license dist.unpackedSize 2>&1 | tail -4; timeout 100 npm view embla-carousel version license dist.unpackedSize 2>&1|tail -4)
df -h /workspace | tail -1
echo "K8 probe1 done"
