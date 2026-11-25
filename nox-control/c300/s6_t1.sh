echo S4RUN:s6_t1
cd /workspace/nox/web/site; grep -o '<body[^>]*>' settings.html; grep -c 'nox-s6-lead' settings.html; grep -o '<div class="ph">.\{0,120\}' settings.html | head -2
