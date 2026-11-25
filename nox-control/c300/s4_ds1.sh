echo S4RUN:s4_ds1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-training.js nox-s4-projects.js nox-s4-projects.css nox-s4-cal.js nox-s4-downloads.js nox-s4-svc.js nox-s4-memory.js nox-s4-lead.js nox-s4-glass.js; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || echo FAIL $f; done; grep -c "sl-button" nox-s4-training.js nox-s4-memory.js
