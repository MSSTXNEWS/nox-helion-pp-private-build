echo "C300: w_s1"
N=/workspace/nox; S=$N/web/site
for p in /api/notes /api/zzzz /api/status /api/nox-live; do echo -n "$p "; curl -s -m 5 -w ' %{http_code}\n' "http://127.0.0.1:8091$p" | cut -c1-90; done
ls $S/vendor/hls.js $S/vendor/hls.js/dist 2>&1 | head -8; ls $S/vendor/vidstack/player 2>&1 | head -8
wc -c $S/tv.html; sed 's/<[^>]*>/ /g' $S/tv.html | tr -s ' \n' ' ' | cut -c1-600; grep -o '<script[^>]*src="[^"]*"' $S/tv.html | sed 's/.*src=//' | tr '\n' ' '
grep -n -o "vidstack[^\"' ]*" $S/cinema.html | head -5
grep -E 'AXE|VISION' $N/agent/out/dcqa.out | cut -c1-300
