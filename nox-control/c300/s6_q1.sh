echo S4RUN:s6_q1
cd /workspace/nox/web/site
grep -o "<sl-select[^>]*>\|<select[^>]*>" nox-s2-studio.js | head; grep -o "stR[^;]\{0,120\}" nox-s2-studio.js | head -6
