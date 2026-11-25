echo S4RUN:s4_rc11
S=/workspace/nox/web/site
ls $S/vendor/nox-x/tabulator $S/vendor/nox-x/tabulator/dist 2>&1 | head -20
grep -n "async function coreGraph" -A14 $S/nox-brain-x.js | cut -c1-240
grep -n "^const go\|const go =" $S/nox-brain-x.js | cut -c1-400
grep -n "function section" $S/nox-brain-x.js | cut -c1-300
grep -n "NOXds" $S/nox-ds.js | head -12 | cut -c1-200
grep -n "unavailable\|empty" $S/nox-ds.js | head -8 | cut -c1-240
