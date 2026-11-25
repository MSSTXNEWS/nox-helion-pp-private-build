echo S4RUN:s6_p7
cd /workspace/nox/web/site
head -c 1800 map.html | grep -v "^$"; echo ----; grep -o '<script[^>]*>' map.html; echo ---; grep -o '<link[^>]*>' news.html | head -12; grep -o '<script[^>]*>' news.html | head -14; grep -rn "shoelace.js\|shoelace/cdn" nox-nav.js nox-dock-pop.js nox-fx.js 2>/dev/null | head -4 | cut -c1-200
