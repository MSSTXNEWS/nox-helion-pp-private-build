echo S4RUN:s4_train1
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; cp -n training.html training.html.bak_s4_1
curl -fsSL $R/nox-s4-training.js -o nox-s4-training.js && curl -fsSL $R/nox-s4-training.css -o nox-s4-training.css || exit 1
grep -q nox-s4-training training.html || python3 - <<'P'
p='/workspace/nox/web/site/training.html';t=open(p).read()
t=t.replace('</head>','<link rel="stylesheet" href="./nox-s4-training.css"></head>',1)
t=t.replace('</body>','<script src="./nox-s4-training.js" defer></script>\n</body>',1)
open(p,'w').write(t)
P
mkdir -p qa/rework; echo "S4 training: чат-контекст, лента событий, ntfy, карточки->шина" > qa/rework/training.fixed
echo "== registry"; python3 -c "
import json;c=json.load(open('qa/registry.json'))['commands']
print(len(c));print([k for k in c if any(x in k.lower() for x in ('train','distill','apply','download','export','ntfy','push'))])"
grep -n -i ntfy /workspace/nox/web/pkg/server/svc_registry.json | head -5
curl -s -o /dev/null -w 'training %{http_code}\n' 127.0.0.1:8091/web/training.html; curl -s -m5 -o /dev/null -w 'ntfy %{http_code}\n' -X POST -d test 127.0.0.1:8091/svc/ntfy/nox-alerts-probe
