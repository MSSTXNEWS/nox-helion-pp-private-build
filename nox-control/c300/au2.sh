#!/bin/bash
cd /workspace/nox/web/site
for l in fullcalendar leaflet drawflow vis-timeline sortable plyr kanban jkanban muuri gridstack; do echo "$l: $(grep -rlio "$l" --include=*.js --include=*.html . 2>/dev/null | grep -v vendor | head -4 | tr '\n' ' ')"; done
grep -rhoE "https?://(cdn|unpkg|esm|cdnjs)[^\"' )]+" --include=*.js --include=*.html . 2>/dev/null | grep -v "^./vendor" | sort | uniq -c | sort -rn | head -15
grep -rhoE "(vendor|/web/vendor)/[a-zA-Z0-9._-]+/" nox-*.js *.html 2>/dev/null | sort | uniq -c | sort -rn | head -30
ss -ltnp | grep -E "bridge|102999" | head; grep -n "port\|PORT" /workspace/nox/integration/drive_media_20261123/bridge.py | head -5 | cut -c1-140
ls /workspace/nox/integration | head -30 | tr '\n' ' '
