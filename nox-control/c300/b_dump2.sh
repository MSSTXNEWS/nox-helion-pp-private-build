S=/workspace/nox/web/site
sed -n 1,60p $S/nox-p-media.js | cut -c1-900
echo "#### css"; grep -n "^\.tag\|^\.card\|^\.empty\|^\.acts\|^\.pill\|^\.seg\|^\.fld\|^\.kick\|--[a-z-]*:" $S/nox-pages.css | head -40 | cut -c1-260
grep -n "^:root" -A25 $S/nox-wow.css | head -50 | cut -c1-200
