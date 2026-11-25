#!/bin/bash
S=/workspace/nox/web/site
cd $S
T=bak_s3_1
D=/workspace/nox/web/site
HERE=$(dirname "$0")
for f in nox-dock-pop.js nox-dock-pop.css; do [ -f $S/$f.$T ] || cp $S/$f $S/$f.$T; done
SRC=/tmp/s3_menu1_src; rm -rf $SRC; mkdir -p $SRC
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in nox-dock-pop.js nox-dock-pop.css s3_menu_build3.py; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o $SRC/$f && echo got $f; done
cp $SRC/nox-dock-pop.js $S/nox-dock-pop.js; cp $SRC/nox-dock-pop.css $S/nox-dock-pop.css
/workspace/nox/venv/bin/python $SRC/s3_menu_build3.py
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
echo "--- menu_plan head"; head -30 $S/qa/menu_plan.md
# --- чёрное солнце, порядок шапки, подключение ко всем страницам
for f in nox-sun-x.js nox-sun-x.css nox-menu-x.css; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o $SRC/$f && cp $SRC/$f $S/$f && echo placed $f; done
ni=0; nd=0
for f in $S/*.html; do
  b=$(basename $f); grep -q "nox-shell\|nox-nav.js\|nox-pult.js" $f || continue
  if ! grep -q 'nox-sun-x.js' $f; then cp $f $f.$T 2>/dev/null; sed -i 's#</body>#<script src="./nox-sun-x.js" defer></script>\n</body>#' $f; ni=$((ni+1)); fi
  grep -q 'nox-menu-x.css' $f || sed -i 's#</head>#<link rel="stylesheet" href="./nox-menu-x.css">\n</head>#' $f
  grep -q 'nox-dock-pop.js' $f || { sed -i 's#</body>#<script src="./nox-dock-pop.js" defer></script>\n</body>#' $f; nd=$((nd+1)); }
done
echo "sun injected: $ni, dockpop injected: $nd"
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
