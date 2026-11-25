echo S4RUN:s4_dl1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-training.js nox-s4-projects.css nox-s4-downloads.js; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
cp -n downloads.html downloads.html.bak_s4_1
grep -q nox-s4-downloads downloads.html || python3 - <<'P'
p='/workspace/nox/web/site/downloads.html';t=open(p).read()
t=t.replace('</head>','<link rel="stylesheet" href="./nox-s4-projects.css"></head>',1)
t=t.replace('</body>','<script src="./nox-s4-downloads.js" defer></script>\n</body>',1)
open(p,'w').write(t)
P
echo "S4 downloads: Filebrowser iframe" > qa/rework/downloads.fixed
curl -s -m5 -D- -o /dev/null 127.0.0.1:8091/svc/filebrowser/ | head -8
