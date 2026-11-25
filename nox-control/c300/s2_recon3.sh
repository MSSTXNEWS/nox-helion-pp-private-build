#!/bin/bash
S=/workspace/nox/web/site
for f in music news studio; do echo "=== $f.html"; sed -n '/<body/,/<script/p' $S/$f.html | cut -c1-400 | head -40; done
for f in nox-music-x.js nox-news-x.js nox-studio-x.js nox-cinema-x.js; do echo "=== $f $(wc -c <$S/$f)"; head -c 3200 $S/$f; echo; done
echo "=== vars"; grep -o '\-\-[a-z0-9-]*:[^;]*' $S/nox-wow.css | head -50
echo "=== page css"; grep -n '\.page\b\|\.wrap\b\|\.card\b\|\.ph\b' $S/nox-pages.css | head -15 | cut -c1-240
echo "=== img svc"; curl -s -m5 http://127.0.0.1:8091/img/status | head -c 300; echo; curl -s -m5 http://127.0.0.1:8091/api/news 2>&1 | head -c 200; ls $S/vendor/swiper $S/vendor/nox-lib $S/vendor/wavesurfer.js | head -30
ls $S/data 2>/dev/null | head; ls /workspace/nox/web/build/node_modules 2>/dev/null | head -40
