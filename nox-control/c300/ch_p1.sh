echo "C300: ch_p1"
S=/workspace/nox/web/site; cd $S
ls -l --time-style=+%H:%M:%S nox-theme.js nox-wow-bg.js nox-nav.js nox-graphite.css nox-graphite-map.css nox-motion.js 2>&1
date +%H:%M:%S
grep -c TH-GRAPHITE nox-wow-bg.js nox-ds.js nox-actions.js
curl -s -m5 localhost:8091/web/chat.html | grep -o 'data-nox-theme[^>]\{0,40\}\|nox-graphite[a-z-]*\.css' | sort | uniq -c
curl -s -m5 localhost:8091/web/nox-theme.js | wc -c
ls /workspace/nox/web | head -30
tail -5 /workspace/nox/web/th_gr7.ts 2>&1
ls -t /workspace/nox/state/*.out 2>/dev/null | head -5
