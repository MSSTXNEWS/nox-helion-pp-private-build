S=/workspace/nox/web/site
echo "== wow.js msg render"; grep -n -oE ".{0,160}(class=\\\\?\"(m |msg|bub|think|txt|act)|className *= *'(m|msg)).{0,200}" $S/nox-wow.js | head -30 | cut -c1-420
echo "== wow.js size/fn"; wc -c $S/nox-wow.js; grep -n -oE "(async )?function (send|renderMsg|addMsg|append[A-Za-z]*|stream[A-Za-z]*|regen[A-Za-z]*|rate|feedback)[A-Za-z]*\(" $S/nox-wow.js | head -20
grep -n -oE ".{0,100}api/(chat|feedback).{0,160}" $S/nox-wow.js | head -8
echo "== pages"; for p in consciousness organism soul growth selffeel training index; do echo "--- $p $(wc -c < $S/$p.html)"; grep -n -E "<script|<link|data-page" $S/$p.html | cut -c1-200 | head -25; done
echo "== vendor dirs"; ls $S/vendor/fx $S/vendor/nox-wow $S/vendor/tsparticles $S/vendor/motion $S/vendor/gridstack $S/vendor/nox-lib $S/vendor/nox-x $S/vendor/nox-extra $S/vendor/glasskit $S/vendor/licenses 2>&1 | head -120
find /workspace/nox -maxdepth 6 \( -iname "echarts*" -o -iname "*xyflow*" -o -iname "3d-force-graph*" -o -iname "llm-viz*" \) -not -path "*/proc/*" 2>/dev/null | head
ls /workspace/nox/tools/node; /workspace/nox/tools/node/bin/node -v; ls /workspace/nox/tools/node/bin
