#!/bin/bash
S=/workspace/nox/web/site
cd $S
for u in /api/traits /api/identity /api/chat/health /glm/v1/nox/stats /api/nox/status /api/sys /api/nox/agents /svc/_status; do echo "## $u"; curl -s -m 8 localhost:8091$u | head -c 700; echo; done
echo "#### nox-p-settings.js"; head -c 3500 nox-p-settings.js; echo
echo "#### prefs keys"; grep -o "localStorage[^;]\{0,80\}" nox-theme.js | head -12
echo "#### shell"; sed -n 1,16p nox-shell.js | cut -c1-1200
echo "#### nav.js header"; grep -n "href=\|HEAD\|hdr\|topbar" nox-nav.js | cut -c1-240 | head -30
echo "#### sun in nav"; grep -n -i "sun" nox-nav.js nox-shell.js nox-dock.js | cut -c1-200 | head -12
echo "#### voice tts"; grep -n "speak\|rate" nox-api.js | cut -c1-160 | head -8
echo "#### favs/recents"; grep -ln "nox.nav.recent\|nox.fav" *.js
echo "#### worlds"; grep -ln "nox-world\|data-nox-world\|Glacier\|setWorld" *.js *.css *.html 2>/dev/null | head; grep -n "Glacier" *.js *.css 2>/dev/null | cut -c1-300 | head -5; grep -n "world" nox-theme.js nox-glass.js 2>/dev/null | cut -c1-200 | head -10
echo "#### dock ic"; grep -n "const ic\|ic = " nox-dock.js | cut -c1-300 | head -3
echo "#### drive proxy"; curl -s -m 8 "localhost:8091/drive/" | head -c 400; echo; curl -s -m 8 "localhost:8091/drive/health" | head -c 300; echo
echo "#### motion100 anywhere"; ls /workspace/nox 2>/dev/null | head -40; find /workspace -iname "*motion100*" -o -iname "*MOTION100*" 2>/dev/null | head -5
echo "#### states"; grep -ln "nox-state\|data-nox-state\|listening" *.js | head
