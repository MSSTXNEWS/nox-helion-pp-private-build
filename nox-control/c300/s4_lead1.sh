echo S4RUN:s4_lead1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-lead.js nox-s4-lead.css nox-s4-svc.js; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
for pr in mail:mail messenger:messenger social:social calls:calls contacts:contacts book-reader:book-reader games:games finance:finance notifications:notifications map:map; do p=${pr%%:*}; k=${pr##*:}; [ -f $p.html ] || continue; cp -n $p.html $p.html.bak_s4_1
 grep -q nox-s4-lead $p.html || python3 - $p $k <<'P'
import sys;p='/workspace/nox/web/site/%s.html'%sys.argv[1];k=sys.argv[2];t=open(p).read()
extra='<link rel="stylesheet" href="./vendor/nox-extra/leaflet.css">' if k=='map' else ''
t=t.replace('</head>',extra+'<link rel="stylesheet" href="./nox-s4-lead.css"></head>',1)
lf='<script src="./vendor/nox-extra/leaflet.js"></script>' if k=='map' and 'leaflet.js' not in t else ''
t=t.replace('</body>',lf+'<script src="./nox-s4-lead.js" data-lead="%s" defer></script>\n</body>'%k,1)
open(p,'w').write(t)
P
 echo "S4 $p: раскладка лидера ($k)" > qa/rework/$p.fixed; echo $p $(grep -c nox-s4-lead $p.html); done
# memos в блок заметок на memory
grep -q 'memos:' memory.html || sed -i 's|</body>|<script src="./nox-s4-svc.js" data-svc="memos:Заметки (Memos)" defer></script>\n</body>|' memory.html
