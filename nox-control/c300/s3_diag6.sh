#!/bin/bash
S=/workspace/nox/web/site
echo "== D6"; grep -n "jupiter\|saturn" $S/nox-wow-data.js | cut -c1-400 | head -6
echo "== worlds"; grep -n "mount\|class=\|innerHTML\|tile\|btn" $S/nox-worlds.js | cut -c1-260 | head -30
grep -n "nxw\|\.world" $S/nox-worlds.css | cut -c1-200 | head -25
