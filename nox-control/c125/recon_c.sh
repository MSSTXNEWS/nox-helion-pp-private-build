#!/bin/bash
# разведка: npm_modules_with_dependencies (пакеты верхнего уровня) и точки входа нужных
N=/root/nox/dl/drive/x/npm_modules_with_dependencies; cd $N; ls | head -3
B=$(ls -d node_modules 2>/dev/null || ls -d */node_modules | head -1); echo "base=$B"; cd $B 2>/dev/null || cd .
for p in cytoscape wavesurfer.js @xterm/xterm @fullcalendar/core driver.js @rive-app/canvas sortablejs; do [ -f $p/package.json ] && python3 -c "
import json,sys;j=json.load(open('$p/package.json'));print('$p',j.get('version'),j.get('license'),'main=',j.get('main'),'module=',j.get('module'),'browser=',j.get('browser'))" || echo "$p -"; done
ls cytoscape/dist 2>/dev/null | head -8 | tr '\n' ' '; echo; ls @xterm/xterm/lib @xterm/xterm/css 2>/dev/null | tr '\n' ' '; echo
ls | wc -l
