#!/bin/bash
S=/workspace/nox/web/site
grep -n "cSee" $S/photo.html | cut -c1-300
grep -n "<button" $S/photo.html | head -8 | cut -c1-260
grep -n "attrs" $S/photo.html $S/nox-s2-photo.js | head -8 | cut -c1-260
ls $S/nox-photo*.js $S/photo*.js 2>/dev/null
