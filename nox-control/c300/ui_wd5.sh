echo "C300: ui_wd5"
F=/workspace/nox/web/v29src/FASTWOW/site
for f in nox-cinematic-worlds.js nox-cinematic-worlds.css nox-world-themes.css; do echo "B64START $f"; base64 -w0 $F/$f; echo; echo "B64END"; done
grep -o "@import[^;]*;\|url([^)]*)" $F/nox-cinematic-worlds.css | sort -u | head
grep -n "nox-world-themes\|nox-world-controls\|nox-theme-header" $F/index.html | cut -c1-200 | head -5
