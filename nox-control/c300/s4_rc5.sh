echo S4RUN:s4_rc5
S=/workspace/nox/web/site
cd $S; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src; curl -fsSL "$R/nox-s4-projects.css?t=$(date +%s)" -o nox-s4-projects.css
for p in calendar events memory settings; do echo "== $p"; grep -n "<script\|fullcalendar" $p.html | cut -c1-150 | head -12; sed -n '/<main/,/<\/main>/p' $p.html | cut -c1-500 | head -14; done
