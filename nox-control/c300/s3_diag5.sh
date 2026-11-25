#!/bin/bash
S=/workspace/nox/web/site
echo "== D5"; for p in music news studio cinema settings index; do echo $p $(grep -c "nox-menu-x.css" $S/$p.html) $(grep -c "nox-planets3d.js" $S/$p.html) $(grep -c "nox-v14-planet.js" $S/$p.html); done
ls -l $S/nox-planets3d.js; head -c 2500 $S/nox-planets3d.js
echo; echo "== tiles"; grep -n "planets/2k\|'2k'\|2k/" $S/*.js | cut -c1-240 | head -12
echo "== wowdata"; grep -on ".\{80\}nox-mercury.\{120\}" $S/nox-wow-data.js | head -3
echo "== menu-x"; head -c 1200 $S/nox-menu-x.css
