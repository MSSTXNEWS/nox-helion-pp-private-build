echo "C300: k4_probe_3"
S=/workspace/nox/web/site; cd $S
echo "== atlas js 30-52"; sed -n 30,52p nox-atlas-s1.js | cut -c1-420
echo "== atlas.html body"; sed -n '/<body/,$p' atlas.html | cut -c1-300 | head -40
echo "== calendar.html"; sed -n '/<body/,$p' calendar.html | cut -c1-300 | head -40
echo "== cal js"; grep -nE "FullCalendar|events|fetch\(|/cal/" nox-s4-cal.js nox-p-calendar.js | cut -c1-240 | head -30
echo "== news.html"; sed -n '/<body/,$p' news.html | cut -c1-300 | head -15
echo "== news js"; grep -nE "nwRoot|fetch\(|class=\"nw-|topics|theme" nox-s2-news.js | cut -c1-240 | head -25
echo "== index body"; sed -n '/<body/,$p' index.html | cut -c1-260 | head -40
echo "== photo"; grep -nE "id=\"(expP|noxBox|fie|gP|gS|aBg)\"" photo.html | cut -c1-300
echo "== system"; sed -n '/<body/,$p' system.html | cut -c1-260 | head -22
