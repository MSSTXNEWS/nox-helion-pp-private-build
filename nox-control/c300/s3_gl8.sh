S=/workspace/nox/web/site
echo "== GL8"; head -c 1500 $S/nox-cmd.js; echo; grep -n "NOXcmd" $S/nox-actions.js | head -4 | cut -c1-220
sed -n 18,34p $S/nox-nav-x.js | cut -c1-300
grep -n "soon\|widgets" $S/nav.json | head -3 | cut -c1-200; /workspace/nox/venv/bin/python -c "
import json;n=json.load(open('$S/nav.json'));g=[x for x in n['groups'] if x['group']=='ВИДЖЕТЫ'][0];print(json.dumps(g,ensure_ascii=False)[:900]);print(n['pages'] if not isinstance(n['pages'],dict) else list(n['pages'].items())[:2])"
grep -n "sl-range\|sl-switch" $S/nox-settings-tabs.js | head -3 | cut -c1-160; grep -n "autoloader\|shoelace.js\|shoelace-autoloader" $S/nox-settings-tabs.js $S/settings.html | head -3 | cut -c1-200
