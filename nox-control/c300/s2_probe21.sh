#!/bin/bash
S=/workspace/nox/web/site
grep -n "mLoop" $S/music.html $S/nox-p-media.js $S/nox-s2-music.js 2>/dev/null | cut -c1-300 | head
grep -n "outline\|focus" $S/nox-s2-tv.css | head -8 | cut -c1-200
