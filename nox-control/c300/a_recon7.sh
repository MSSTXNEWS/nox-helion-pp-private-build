S=/workspace/nox/web/site
grep -n "streamTurn" $S/nox-wow.js | cut -c1-120 | head -4
awk '/function streamTurn|streamTurn *=/{f=1} f{print substr($0,1,800); n++} n>22{exit}' $S/nox-wow.js
grep -n "^import\|from '\./" $S/nox-wow.js | head -12 | cut -c1-200
