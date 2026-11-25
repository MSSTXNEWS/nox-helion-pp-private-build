W=/workspace/nox/web; S=$W/site; cd $S
echo "== libs"; find . /workspace/nox/web/build -maxdepth 6 \( -iname 'echarts*.js' -o -iname 'frappe*' -o -iname 'excalidraw*' -o -iname '*blocknote*' -o -iname 'cytoscape*.js' -o -iname 'sortable*.js' -o -iname 'fullcalendar*.js' \) -not -path '*/node_modules/*/node_modules/*' 2>/dev/null | head -40
ls $W/build 2>/dev/null | head; ls $W/build/node_modules 2>/dev/null | head -60
echo "== training.html"; cat training.html
echo "== dispatcher.html"; cat dispatcher.html | head -c 2800
echo "== board.html"; cat board.html | head -c 2600
echo "== bus"; ls /workspace/nox/web/site | grep -i -E "bus|cmd|nox-.*js" | head -40
grep -o '"/[a-z]*/[^"]*"' $W/pkg/server/web_server.py 2>/dev/null | sort -u | head -60
echo "== ntfy"; curl -s -m5 localhost:8091/svc/ntfy | head -c 200
echo "== events"; cat events.html | head -c 1500
