#!/bin/bash
S=/workspace/nox/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
echo "== D4"; ls -l $S/nox-4k.css; md5sum $S/nox-4k.css; curl -fsS "$RAW/nox-4k.css?v=$(date +%s)" | md5sum; curl -fsS "$RAW/nox-4k.css?v=$(date +%s)" | head -3
echo "== refs"; grep -on ".\{60\}nox-mercury.\{80\}" $S/nox-v14-planet.js $S/nox-wow-data.js | head -5
echo "== p3d"; grep -n "mercury\|jupiter\|saturn\|urano\|uranus\|neptun\|TEX\|file\|\.jpg" $S/nox-planets3d.js | cut -c1-220 | head -40
echo "== tb css"; grep -n "tb-l\b\|\.tb-l{" $S/*.css | cut -c1-260 | head -15
echo "== sunjs pages"; grep -L "nox-sun-x.js" $S/{music,news,studio,cinema,settings}.html
grep -c "nox-s2.css" $S/music.html; grep -n "\.tb\b[^-]\|\.tb-t\|\.tb-l" $S/nox-s2.css | cut -c1-260 | head -20
