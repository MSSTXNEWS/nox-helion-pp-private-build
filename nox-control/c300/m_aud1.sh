#!/bin/bash
# M: аудит меню и разделов (только чтение)
echo "C300: m_aud1.sh"
S=/workspace/nox/web/site
echo "== nav.json size"; wc -c $S/nav.json
echo "== nav.json"; cat $S/nav.json | head -c 20000
echo; echo "== html count"; ls $S/*.html | wc -l
echo "== html title + stub hints"
for f in $S/*.html; do
  b=$(basename $f)
  t=$(grep -o '<title>[^<]*</title>' $f | head -1 | sed 's/<[^>]*>//g' | cut -c1-90)
  sz=$(wc -c < $f)
  st=$(grep -oiE 'ПЕРЕНЕСЕН[^<]{0,60}|заглушк[^<]{0,40}|в разработке|coming soon' $f | head -2 | tr '\n' '|' | cut -c1-120)
  echo "$b | $sz | $t | $st"
done
echo "== menu sources"
grep -l -E 'nav\.json|nox-dock-pop|nox-ninja|nox-nav|nox-pult|nox-shell' $S/*.js $S/*.html 2>/dev/null | xargs -n1 basename
echo "== nox-dock-pop.js (head)"; head -c 6000 $S/nox-dock-pop.js 2>/dev/null
echo; echo "== nox-ninja.js nav refs"; grep -n -E 'nav|pages|groups' $S/nox-ninja.js 2>/dev/null | head -40 | cut -c1-220
