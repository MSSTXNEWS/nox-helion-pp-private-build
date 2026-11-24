#!/bin/bash
S=/workspace/nox/web/site
python3 -c "
import json;d=json.load(open('$S/nav.json'))
for g in d['groups']: print(g['group']+': '+', '.join(i['file'].replace('.html','')+('*' if i.get('soon') else '') for i in g['items']))
print('PAGES', len(d['pages']), str(d['pages'][:3])[:200]); print('SOON', str(d['soon'][:3])[:200])
"
sed -n 84,150p $S/nox-shell.js | cut -c1-210
