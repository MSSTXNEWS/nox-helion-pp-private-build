#!/bin/bash
S=/workspace/nox/web/site
cd $S
echo "#### pages"
for f in *.html; do
 sz=$(stat -c %s $f); t=$(grep -o '<title>[^<]*' $f | head -1 | cut -c8-60)
 fl=""; grep -qi "перенесена" $f && fl="$fl MOVED"; grep -qi 'http-equiv="refresh"' $f && fl="$fl REFRESH"; grep -qi "скоро\|coming soon\|в разработке" $f && fl="$fl SOON"
 nl=$(grep -c "" $f); echo "$f $sz $nl [$t]$fl"
done
echo "#### shell"; sed -n 1,30p nox-shell.js | cut -c1-1500
echo "#### where nav used"; grep -ln "nav.json" *.js | tr '\n' ' '
echo "#### dockpop"; cat nox-dock-pop.css
echo "#### sun"; grep -n "sun\|solar" nox-nav.js | head -10 | cut -c1-200; grep -o 'id="[a-zA-Z]*[sS]un[a-zA-Z]*"' *.html | sort | uniq -c | head
echo "#### head of index topbar"; grep -n "tb\(Search\|Sun\|Mini\)\|class=\"sun\|topbar" nox-shell.js | cut -c1-260 | head -12
