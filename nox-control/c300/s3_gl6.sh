S=/workspace/nox/web/site
echo "== GL6"; grep -ln "' / '\|\" / \"\| / '" $S/nox-*.js | head; grep -n "crumb\|breadcrumb" $S/nox-*.js | cut -c1-260 | head -12
