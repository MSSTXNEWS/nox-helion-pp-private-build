echo S4RUN:s4_mem10
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src
cd $S; for f in nox-s4-memory.js nox-s4-memory.css; do curl -fsSL "$R/$f?t=$(date +%s)" -o $f || exit 1; done
cp -n memory.html memory.html.bak_s4_1
grep -q nox-s4-memory memory.html || python3 - <<'P'
p='/workspace/nox/web/site/memory.html';t=open(p).read()
t=t.replace('<script src="./nox-theme.js"></script>','<script src="./nox-s4-memory.js"></script><link rel="stylesheet" href="./nox-s4-memory.css"><script src="./vendor/cytoscape/dist/cytoscape.min.js"></script><script src="./nox-theme.js"></script>',1)
open(p,'w').write(t)
P
grep -c nox-s4-memory memory.html
# training: тот же честный текст
sed -i 's/память недоступна: \/memory\/api отвечает 400 (нужен текст запроса)/сервер памяти не развёрнут/' nox-s4-training.js; grep -c "сервер памяти не развёрнут" nox-s4-training.js
echo "S4 memory: граф Cytoscape (Obsidian) по /search, честный статус сервера памяти" > qa/rework/memory.fixed
