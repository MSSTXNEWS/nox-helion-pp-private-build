echo S4RUN:s6_p13
cd /workspace/nox/web/site
grep -n -o ".\{70\}\.cover.\{90\}" nox-s2-music.js | head -10
grep -n -o ".\{40\}Image().\{60\}" nox-s2-music.js | head -4
