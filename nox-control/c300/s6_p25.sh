echo S4RUN:s6_p25
cd /workspace/nox/web/site
grep -n "archive.org\|fetch(" nox-s2-music.js | cut -c1-240 | head -12
grep -n "cover" nox-s2-music.js | cut -c1-200 | head -8
