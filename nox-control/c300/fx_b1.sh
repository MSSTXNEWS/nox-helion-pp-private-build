S=/workspace/nox/web/site
echo ==manual; wc -c $S/nox-manual.js; cat $S/nox-manual.js | cut -c1-600 | head -80
echo ==home; grep -n "404\|health\|недоступно\|Шлюз\|Глубокий\|Быстрый\|8104\|8200\|/glm/\|memory" $S/nox-p-home.js | cut -c1-300 | head -40
echo ==minichat; grep -n "пустой\|content\|done\|NDJSON\|split" $S/nox-minichat.js | cut -c1-260 | head -40
echo ==MUSIC; grep -n "^MUSIC\|MUSIC *=" /workspace/nox/web/pkg/server/web_server.py | head -3
