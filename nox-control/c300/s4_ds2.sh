echo S4RUN:s4_ds2
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-projects.css nox-s4-lead.js nox-s4-glass.js nox-s4-svc.js; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || echo FAIL $f; done
echo S4SLIDER=$(grep -c S4SLIDER nox-brain-x.js) S4THEME=$(grep -c S4THEME nox-brain-x.js)
grep -o "registerTheme('[a-z]*'" nox-brain-x.js | head -2
grep -n "type: 'slider'" nox-brain-x.js | cut -c1-420
ls -la --time-style=+%H:%M nox-brain-x.js* | awk '{print $6,$7}'
