echo S4RUN:s4_cal1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-cal.js nox-s4-cal.css nox-s4-projects.css; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
cp -n calendar.html calendar.html.bak_s4_1
grep -q nox-s4-cal calendar.html || python3 - <<'P'
p='/workspace/nox/web/site/calendar.html';t=open(p).read()
k='<script src="./vendor/nox-extra/fullcalendar.global.min.js"></script>'
assert k in t
t=t.replace(k,k+'<script src="./nox-s4-cal.js"></script><link rel="stylesheet" href="./nox-s4-cal.css">',1)
open(p,'w').write(t)
P
echo "S4 calendar: Google Calendar (views, mini-cal)" > qa/rework/calendar.fixed; cp qa/rework/calendar.fixed qa/rework/events.fixed
grep -c nox-s4-cal calendar.html
