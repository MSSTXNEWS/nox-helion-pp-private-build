S=/workspace/nox/web/site
grep -n "onDelta\|fetch(\|\.type\|JSON.parse" $S/nox-turn.js | cut -c1-330 | head -30
