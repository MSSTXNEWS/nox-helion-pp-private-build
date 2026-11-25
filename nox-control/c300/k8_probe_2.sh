echo "C300: k8_probe_2"
S=/workspace/nox/web/site; cd $S
head -c 260 vendor/fuse.js/fuse.js.iife.js; echo; head -c 260 vendor/embla-carousel/embla-carousel.iife.js; echo
grep -n "^| fuse\|^| embla" vendor/VENDOR_INDEX.md VENDOR_INDEX.md 2>/dev/null | cut -c1-300; ls vendor/*/package.json 2>/dev/null | grep -i "fuse\|embla"
tail -c 600 vendor/fuse.js/fuse.js.iife.js | head -c 400; echo
for f in ts-fsrs/ts-fsrs.iife.js d3-shape/d3-shape.iife.js suncalc/suncalc.iife.js; do echo "== $f"; head -c 220 vendor/$f; echo; done
ls vendor/gsap vendor/canvas-confetti | head; 
echo ---LIVE; head -c 900 data/live.json; echo; echo ---ARB; head -c 700 data/arbiter.json; echo; echo ---ORG; head -c 500 data/organs_hist.jsonl; echo; wc -l data/organs_hist.jsonl; echo ---TRAIN; head -c 400 data/train_logs.json; echo
echo ---FIN; grep -o "localStorage[^;]\{0,80\}" nox-fin-s1.js | sort -u | head -8; head -c 1200 finance.html | tail -c 700; grep -c "" nox-fin-s1.js; grep -o "fetch([^)]*)" nox-fin-s1.js | sort -u | head
echo ---SYS; grep -o "fetch([^)]*)" nox-p-system.js nox-s4-grafana.js | sort -u | head; grep -o 'id="tiles"[^>]*>' system.html
echo ---CONS; grep -o 'class="[^"]*"' consciousness.html | sort -u | head -15
echo ---CIN; grep -o "<video[^>]*>" cinema.html nox-s2-cinema.js | head -3; grep -o "createElement('video')\|vds-media\|media-player" nox-s2-cinema.js | sort -u | head
echo ---TRN; grep -o "fetch([^)]*)" nox-p-training.js nox-s4-training.js | sort -u | head
grep -o "sl-[a-z-]*" nox-ds.js | sort -u | head -30 | tr '\n' ' '
echo "K8 probe2 done"
