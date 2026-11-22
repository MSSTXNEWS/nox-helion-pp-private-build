#!/bin/bash
W=/root/nox/web
df -h /root | tail -1
echo "ls web: $(ls $W | tr '\n' ' ')"
echo "pc: $(ls $W/pc | head -40 | tr '\n' ' ')"
echo "== 8091:"; ss -ltnp | grep -E ":(8091|8090)" | cut -c1-140; pgrep -af web_server | cut -c1-150
echo "== textures:"; find $W -iname '*earth*' -o -iname '*moon*' -o -iname '*mars*' -o -iname '*saturn*' -o -iname '*jupiter*' | head -12
echo "== hdri/metal:"; find $W -iname '*hdr*' -o -iname '*metal*' | grep -v node_modules | head -5
echo "== wow:"; ls $W/pc/vendor/nox-extra $W/pc/vendor/nox-ux 2>&1 | tr '\n' ' '|cut -c1-600; echo
echo "== planets.html refs:"; grep -o 'src="[^"]*"\|href="[^"]*\.css"' $W/planets.html | head -12 | tr '\n' ' '; echo; wc -c $W/planets.html $W/widgets.html $W/projects.html $W/settings.html
echo "== kanban/calendar usage:"; grep -l -i 'Sortable\|fullcalendar' $W/*.html $W/*.js 2>/dev/null | head
echo "== vad refs:"; grep -l -i 'vad-web\|silero\|MicVAD' $W/*.html $W/*.js $W/pc/*.js 2>/dev/null | head
echo "== memory page:"; grep -c 'вспомнил' $W/memory.html; ls $W/*.js | xargs -n1 basename | tr '\n' ' '
