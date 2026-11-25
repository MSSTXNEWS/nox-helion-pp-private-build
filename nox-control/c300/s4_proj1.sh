echo S4RUN:s4_proj1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; cp -n projects.html projects.html.bak_s4_1
for f in nox-s4-projects.js nox-s4-projects.css; do curl -fsSL $R/$f -o $f || exit 1; done
grep -q nox-s4-projects projects.html || python3 - <<'P'
p='/workspace/nox/web/site/projects.html';t=open(p).read()
t=t.replace('</head>','<link rel="stylesheet" href="./vendor/nox-x/gantt/frappe-gantt.min.css"><link rel="stylesheet" href="./nox-s4-projects.css"><script src="./vendor/nox-x/gantt/frappe-gantt.min.js"></script></head>',1)
t=t.replace('</body>','<script src="./nox-s4-projects.js" defer></script>\n</body>',1)
open(p,'w').write(t)
P
echo "S4 projects: Список(Linear)+Гант(Frappe)" > qa/rework/projects.fixed
head -c 300 vendor/nox-x/gantt/frappe-gantt.min.js | head -c 200; grep -c "window.Gantt\|Gantt=" vendor/nox-x/gantt/frappe-gantt.min.js
