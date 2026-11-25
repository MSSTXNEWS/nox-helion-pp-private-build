echo S4RUN:s6_p14
cd /workspace/nox/web/site
grep -n -o ".\{20\}cvStyle *=.\{200\}\|function cvStyle.\{200\}" nox-s2-music.js | head -3
grep -n "\.cv" nox-s2.css | head -5 | cut -c1-200
