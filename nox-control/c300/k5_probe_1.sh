echo "C300: k5_probe_1"
S=/workspace/nox/web/site; cd $S
ls *.html | tr '\n' ' '; echo
ls | grep -E 'nox-k[345]' | tr '\n' ' '; echo
ls vendor | tr '\n' ' ' | head -c 3000; echo
for p in index studio photo music growth cinema assistant voice chat; do echo "== $p"; [ -f $p.html ] && { wc -c $p.html; grep -oE '<(main|section|header|div|video|audio|canvas|img)[^>]*(id|class)="[^"]*"' $p.html | head -14 | cut -c1-110; grep -oE 'src="[^"]*nox[^"]*"' $p.html | head -8 | tr '\n' ' '; echo; }; done
sed -n 1,60p nox-k3-core.js | cut -c1-220
for v in fabric pixi-filters mediapipe-tasks-vision howler typewriter-effect embla-carousel canvas-confetti vidstack transformers-js codemirror rive; do echo "-- $v"; ls vendor/$v* /web/vendor/nox-x/$v* 2>/dev/null | head -5; done
grep -n 'vendor' /workspace/nox/web/site/nox-k4-inbox.js | head -3
