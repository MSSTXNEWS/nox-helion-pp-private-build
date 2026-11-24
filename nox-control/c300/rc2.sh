cd /workspace/nox/web/site
python3 - <<'P'
import json;d=json.load(open('nav.json'))
print(list(d.keys()))
for g in d['groups']: print(g['group'],[i['file'] for i in g['items']])
P
echo ---NAVJS; wc -c nox-nav.js; grep -no "class=\"[a-z0-9_ -]*dock[a-z0-9_ -]*\"\|id=\"[a-z-]*dock[a-z-]*\"\|\.nox-dock[a-z_-]*\|\.nx-[a-z-]*" nox-nav.js | sort -u -t: -k3 | head -40
echo ---SRV; sed -n 120,160p ../pkg/server/web_server.py | cut -c1-220
grep -n "def _proxy" -A25 ../pkg/server/web_server.py | cut -c1-200
echo ---DL; head -c 1800 downloads.html
which php node npm go ffmpeg yt-dlp; node -v; php -v|head -1
