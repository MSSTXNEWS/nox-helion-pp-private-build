#!/bin/bash
S=/workspace/nox/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
cd $S
for f in nox-sun-x.css nox-settings-tabs.css; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3ui2_$f && cp /tmp/s3ui2_$f $S/$f && echo placed $f; done
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
echo "#### dock keys"; grep -on "localStorage[.a-zA-Z]*([^)]\{0,60\})\|ls\.[a-z]*('[^']*'" nox-dock.js | head -20
grep -n "tbFav\|tbBell\|tbNotes" nox-nav.js nox-dock.js nox-home-x.js 2>/dev/null | cut -c1-220 | head
ls pages 2>/dev/null | head -3; grep -rn "tbFav" --include=*.js . 2>/dev/null | cut -c1-200 | head -4
