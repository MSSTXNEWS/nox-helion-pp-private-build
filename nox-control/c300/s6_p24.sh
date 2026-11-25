echo S4RUN:s6_p24
curl -s http://127.0.0.1:8300/ | head -c 200; echo
for u in /index.html /web/ /site/index.html /web/site/music.html /nox/music.html; do echo $u $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8300$u); done
ls -la /proc/2993735/cwd; tr '\0' ' ' </proc/2993735/cmdline; echo
