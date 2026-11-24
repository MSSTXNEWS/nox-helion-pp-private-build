cd /workspace/nox/web/site; touch qa/rework/index.fixed
cat cinema.html | cut -c1-400 | sed -n '12,60p'; echo ====; cat music.html | cut -c1-400 | sed -n '12,50p'
wc -c nox-p-cinema.js nox-p-media.js nox-svc-embed.js
curl -s -m 8 127.0.0.1:8091/svc/jellyfin/System/Info/Public | head -c 400; echo
curl -s -m 8 127.0.0.1:8091/svc/navidrome/rest/ping.view?v=1.16.1\&c=nox\&f=json | head -c 300; echo
ls /workspace/nox/music_lib 2>&1 | head; find /workspace -maxdepth 4 \( -iname "*.mp3" -o -iname "*.flac" -o -iname "*.mkv" -o -iname "*.mp4" \) 2>/dev/null | grep -v "/venv/\|site-packages\|node_modules\|/vendor/" | head -15
ls /workspace/nox | head -60; ls /workspace/nox/state | grep -i "jelly\|navi\|media\|secret\|svc" | head
